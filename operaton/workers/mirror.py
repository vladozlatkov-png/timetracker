"""Mirror Operaton process state into the Audit OS database.

One-way, derived, idempotent — the same contract the Notion engagement cards
already carry ("mirrored one-way from Postgres workflow.* — do not edit here").
The engine is the authority on process control; this only projects it.

`blocked_reason` is rendered in the exact format already on the Notion cards:

    G-WP-CONCLUDED open, G-EVIDENCE-LOCK open · next: fw-je, fw-rp

so the existing Notion sync keeps working with no change.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time

import psycopg

import operaton_client as engine

AUDIT_OS_DSN = os.environ["AUDIT_OS_DSN"]
INTERVAL = int(os.environ.get("MIRROR_INTERVAL_SECONDS", "60"))
DEFINITION_KEY = os.environ.get("PROCESS_DEFINITION_KEY", "statutory-audit")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)
log = logging.getLogger("mirror")

_running = True


def _stop(signum, _frame):
    global _running
    log.info("signal %s received, exiting after this pass", signum)
    _running = False


# --- derivation --------------------------------------------------------------

# Gate code -> predicate over (process variables, step counts).
# Keep these aligned with the gate codes already used on the Notion cards.
GATES: list[tuple[str, callable]] = [
    ("G-SANCTIONS",     lambda v, s: v.get("sanctionsClear") is True),
    ("G-INDEPENDENCE",  lambda v, s: v.get("independenceConfirmed") is True),
    ("G-WP-CONCLUDED",  lambda v, s: s["total"] > 0 and s["done"] >= s["total"]),
    ("G-GC",            lambda v, s: v.get("goingConcernConclusion") in
                                     ("appropriate", "material_uncertainty")),
    ("G-EQCR",          lambda v, s: (not v.get("eqcrRequired")) or v.get("eqcrCleared") is True),
    ("G-EVIDENCE-LOCK", lambda v, s: v.get("evidenceLocked") is True),
]

# Active activity id -> engagement status. First match wins, in this order.
STATUS_BY_ACTIVITY: list[tuple[str, str]] = [
    ("Task_SanctionsCheck",       "acceptance"),
    ("Task_ConfirmIndependence",  "acceptance"),
    ("Task_ApproveMateriality",   "planning"),
    ("Task_ApproveRisk",          "planning"),
    ("Task_LoadRegistry",         "planning"),
    ("Call_Fieldwork",            "fieldwork"),
    ("Task_GoingConcern",         "completion"),
    ("Task_Eqcr",                 "completion"),
    ("Task_CompletionChecklist",  "completion"),
    ("Task_PartnerSignoff",       "reporting"),
    ("Task_IssueReport",          "reporting"),
]


def derive_status(activity_ids: list[str], incidents: int) -> str:
    if incidents:
        return "blocked"
    for activity, status in STATUS_BY_ACTIVITY:
        if activity in activity_ids:
            return status
    return "closed" if not activity_ids else "fieldwork"


def render_blocked_reason(gates_open: list[str], next_steps: list[str]) -> str | None:
    if not gates_open and not next_steps:
        return None
    parts = [f"{g} open" for g in gates_open]
    reason = ", ".join(parts)
    if next_steps:
        reason = f"{reason} · next: {', '.join(next_steps)}" if reason \
            else f"next: {', '.join(next_steps)}"
    return reason


def step_counts(conn: psycopg.Connection, engagement_id: str, total_hint: int | None) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            "select count(distinct step_key) from orchestrator.step_result "
            "where engagement_id = %s and outcome = 'completed'",
            (engagement_id,),
        )
        done = cur.fetchone()[0]
        if total_hint:
            total = total_hint
        else:
            cur.execute("select count(*) from orchestrator.v_steps where phase = 'fieldwork'")
            total = cur.fetchone()[0]
    return {"done": done, "total": total}


def pending_steps(conn: psycopg.Connection, engagement_id: str, limit: int = 6) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "select s.step_key from orchestrator.v_steps s "
            "where s.phase = 'fieldwork' "
            "  and not exists (select 1 from orchestrator.step_result r "
            "                  where r.engagement_id = %s and r.step_key = s.step_key "
            "                    and r.outcome = 'completed') "
            "order by s.sort_order limit %s",
            (engagement_id, limit),
        )
        return [row[0] for row in cur.fetchall()]


# --- one pass ----------------------------------------------------------------

def mirror_instance(conn: psycopg.Connection, instance: dict) -> None:
    instance_id = instance["id"]
    variables = engine.instance_variables(instance_id)
    engagement_id = variables.get("engagementId") or instance.get("businessKey")
    if not engagement_id:
        log.warning("instance %s has no engagementId/businessKey, skipping", instance_id)
        return

    activity_ids = engine.active_activity_ids(instance_id)
    incidents = engine.incident_count(instance_id)
    tasks = engine.open_tasks(instance_id)

    counts = step_counts(conn, engagement_id, variables.get("stepsTotal"))
    gates_open, gates_closed = [], []
    for code, predicate in GATES:
        try:
            satisfied = bool(predicate(variables, counts))
        except Exception:  # noqa: BLE001 — a bad predicate must not stop the mirror
            satisfied = False
        (gates_closed if satisfied else gates_open).append(code)

    next_steps = pending_steps(conn, engagement_id)
    status = derive_status(activity_ids, incidents)
    open_human_tasks = [
        {"id": t["id"], "name": t.get("name"), "assignee": t.get("assignee"),
         "created": t.get("created")}
        for t in tasks
    ]

    with conn.cursor() as cur:
        cur.execute(
            "insert into orchestrator.engagement_process "
            "(engagement_id, process_instance_id, business_key) values (%s, %s, %s) "
            "on conflict (engagement_id) do update set process_instance_id = excluded.process_instance_id",
            (engagement_id, instance_id, instance.get("businessKey")),
        )
        cur.execute(
            "insert into orchestrator.process_state "
            "(engagement_id, status, gates_open, gates_closed, next_steps, "
            " open_human_tasks, incident_count, steps_done, steps_total, "
            " blocked_reason, derived_at) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()) "
            "on conflict (engagement_id) do update set "
            "  status = excluded.status, gates_open = excluded.gates_open, "
            "  gates_closed = excluded.gates_closed, next_steps = excluded.next_steps, "
            "  open_human_tasks = excluded.open_human_tasks, "
            "  incident_count = excluded.incident_count, steps_done = excluded.steps_done, "
            "  steps_total = excluded.steps_total, blocked_reason = excluded.blocked_reason, "
            "  derived_at = now()",
            (engagement_id, status, gates_open, gates_closed, next_steps,
             json.dumps(open_human_tasks), incidents, counts["done"], counts["total"],
             render_blocked_reason(gates_open, next_steps)),
        )
        conn.commit()

    log.info("%s -> %s (%s/%s steps, %s open gates, %s incidents)",
             engagement_id, status, counts["done"], counts["total"],
             len(gates_open), incidents)


def run_pass() -> None:
    instances = engine.process_instances(DEFINITION_KEY)
    if not instances:
        log.debug("no running instances of %s", DEFINITION_KEY)
        return
    with psycopg.connect(AUDIT_OS_DSN) as conn:
        for instance in instances:
            try:
                mirror_instance(conn, instance)
            except Exception:  # noqa: BLE001 — one bad instance must not stop the rest
                log.exception("failed to mirror instance %s", instance.get("id"))


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("mirroring %s every %ss", DEFINITION_KEY, INTERVAL)

    while _running:
        try:
            run_pass()
        except Exception:  # noqa: BLE001 — keep the loop alive
            log.exception("mirror pass failed")
        for _ in range(INTERVAL):
            if not _running:
                break
            time.sleep(1)

    log.info("mirror stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
