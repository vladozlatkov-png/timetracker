"""External task handlers.

Design rule — FAIL LOUDLY:
    A handler whose integration is not configured raises NotConfigured, which
    the worker turns into an engine incident with zero retries. It never
    completes the task with a fabricated success.

    This matters most for `sanctions-check`: an unconfigured screening step that
    silently sets sanctionsClear=true would let an engagement through acceptance
    with no screening performed and no trace that it was skipped. Do not "fix"
    an incident by stubbing a positive result.

Each handler takes the fetched task dict and returns a plain dict of variables
to set on completion (encoded by the caller).
"""

from __future__ import annotations

import json
import os

import psycopg
import requests

from operaton_client import HTTP_TIMEOUT, decode_vars, json_list_var

AUDIT_OS_DSN = os.environ.get("AUDIT_OS_DSN", "")


class NotConfigured(RuntimeError):
    """Raised when a handler's integration endpoint is not configured."""


def _require(env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise NotConfigured(
            f"{env_name} is not set. This step performs no work until it is "
            f"configured; refusing to report success. See operaton/README.md."
        )
    return value


def _db() -> psycopg.Connection:
    if not AUDIT_OS_DSN:
        raise NotConfigured("AUDIT_OS_DSN is not set — cannot reach the Audit OS database.")
    return psycopg.connect(AUDIT_OS_DSN)


def _vars(task: dict) -> dict:
    return decode_vars(task.get("variables"))


# --- handlers ----------------------------------------------------------------

def sanctions_check(task: dict) -> dict:
    """Screen the client against the configured sanctions/PEP provider."""
    url = _require("SANCTIONS_API_URL")
    v = _vars(task)
    resp = requests.post(
        url,
        json={
            "engagementId": v.get("engagementId"),
            "clientCode": v.get("clientCode"),
            "clientName": v.get("clientName"),
        },
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json()

    # Explicit: absence of a decisive answer is NOT a pass.
    if "clear" not in result:
        raise RuntimeError(f"Sanctions provider returned no 'clear' verdict: {result!r}")

    return {
        "sanctionsClear": bool(result["clear"]),
        "sanctionsDetail": json.dumps(result)[:3000],
    }


def load_step_registry(task: dict) -> dict:
    """Read the step registry and hand the engine the fieldwork step list.

    Reads orchestrator.v_steps — repoint that view at the real workflow.*
    registry and nothing here changes.
    """
    with _db() as conn, conn.cursor() as cur:
        cur.execute(
            "select step_key from orchestrator.v_steps "
            "where phase = 'fieldwork' order by sort_order"
        )
        steps = [row[0] for row in cur.fetchall()]

    if not steps:
        raise RuntimeError(
            "orchestrator.v_steps returned no fieldwork steps — the registry is "
            "empty or the view is pointed at the wrong source."
        )

    # Returned pre-encoded: multi-instance needs a real java.util.ArrayList.
    return {"__raw__": {"fieldworkSteps": json_list_var(steps),
                        "stepsTotal": {"value": len(steps), "type": "Long"}}}


def run_audit_step(task: dict) -> dict:
    """Dispatch one audit programme step to the skills stack."""
    url = _require("AUDIT_STEP_DISPATCH_URL")
    v = _vars(task)
    step_key = v.get("auditStep")
    engagement_id = v.get("engagementId")

    with _db() as conn, conn.cursor() as cur:
        cur.execute(
            "select step_name, requires_review from orchestrator.v_steps where step_key = %s",
            (step_key,),
        )
        row = cur.fetchone()
    step_name, requires_review = row if row else (step_key, True)

    resp = requests.post(
        url,
        json={"engagementId": engagement_id, "stepKey": step_key, "stepName": step_name},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json() if resp.content else {}

    with _db() as conn, conn.cursor() as cur:
        cur.execute(
            "insert into orchestrator.step_result "
            "(engagement_id, step_key, process_instance_id, outcome, detail) "
            "values (%s, %s, %s, %s, %s)",
            (engagement_id, step_key, task.get("processInstanceId"),
             "completed", json.dumps(result)),
        )
        conn.commit()

    return {"stepRequiresReview": bool(requires_review), "stepKey": step_key}


def pbc_chase(task: dict) -> dict:
    """Send the periodic outstanding-PBC reminder."""
    url = _require("PBC_CHASE_WEBHOOK")
    v = _vars(task)
    resp = requests.post(
        url,
        json={"engagementId": v.get("engagementId"), "clientCode": v.get("clientCode")},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return {"lastPbcChaseOk": True}


def issue_report(task: dict) -> dict:
    """Issue the signed report and lock the engagement file."""
    url = _require("ISSUE_REPORT_WEBHOOK")
    v = _vars(task)
    resp = requests.post(
        url,
        json={
            "engagementId": v.get("engagementId"),
            "opinionType": v.get("opinionType"),
            "partnerSignoff": v.get("partnerSignoff"),
        },
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json() if resp.content else {}
    return {"evidenceLocked": True, "reportRef": str(result.get("reportRef", ""))}


HANDLERS = {
    "sanctions-check": sanctions_check,
    "load-step-registry": load_step_registry,
    "run-audit-step": run_audit_step,
    "pbc-chase": pbc_chase,
    "issue-report": issue_report,
}
