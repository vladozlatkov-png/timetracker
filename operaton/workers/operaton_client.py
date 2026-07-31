"""Thin Operaton REST client.

Covers only what the workers need. The REST API is Camunda 7 compatible, so
the Camunda 7 REST reference applies verbatim:
https://docs.operaton.org/ (engine-rest)
"""

from __future__ import annotations

import json
import os
from typing import Any

import requests

OPERATON_URL = os.environ.get("OPERATON_URL", "http://localhost:8080/engine-rest")
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT_SECONDS", "30"))


class OperatonError(RuntimeError):
    pass


# --- variable encoding -------------------------------------------------------

def var(value: Any) -> dict:
    """Encode a Python value as an Operaton typed variable."""
    if isinstance(value, bool):
        return {"value": value, "type": "Boolean"}
    if isinstance(value, int):
        return {"value": value, "type": "Long"}
    if isinstance(value, float):
        return {"value": value, "type": "Double"}
    return {"value": value, "type": "String"}


def json_list_var(items: list) -> dict:
    """Encode a list so the engine deserialises it into a java.util.ArrayList.

    Required for multi-instance `collection` expressions: the engine needs a
    real java.util.Collection, not a JSON string. Relies on the Jackson JSON
    dataformat that ships with the distribution.
    """
    return {
        "value": json.dumps(items),
        "type": "Object",
        "valueInfo": {
            "objectTypeName": "java.util.ArrayList",
            "serializationDataFormat": "application/json",
        },
    }


def encode_vars(plain: dict) -> dict:
    return {k: var(v) for k, v in plain.items()}


def decode_vars(raw: dict | None) -> dict:
    """Flatten an Operaton variable map to plain Python values."""
    out: dict = {}
    for name, spec in (raw or {}).items():
        value = spec.get("value")
        if spec.get("type") == "Object" and isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                pass
        out[name] = value
    return out


# --- HTTP --------------------------------------------------------------------

def _request(method: str, path: str, **kwargs) -> Any:
    url = f"{OPERATON_URL}{path}"
    resp = requests.request(method, url, timeout=HTTP_TIMEOUT, **kwargs)
    if resp.status_code >= 400:
        raise OperatonError(f"{method} {path} -> {resp.status_code}: {resp.text[:500]}")
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


def get(path: str, params: dict | None = None) -> Any:
    return _request("GET", path, params=params)


def post(path: str, body: dict | None = None) -> Any:
    return _request("POST", path, json=body or {})


# --- external tasks ----------------------------------------------------------

def fetch_and_lock(worker_id: str, topics: list[str], max_tasks: int = 5,
                   lock_ms: int = 120_000, long_poll_ms: int = 20_000) -> list[dict]:
    return post("/external-task/fetchAndLock", {
        "workerId": worker_id,
        "maxTasks": max_tasks,
        "usePriority": True,
        "asyncResponseTimeout": long_poll_ms,
        "topics": [
            {"topicName": t, "lockDuration": lock_ms, "variables": None}
            for t in topics
        ],
    }) or []


def complete(task_id: str, worker_id: str, variables: dict | None = None) -> None:
    post(f"/external-task/{task_id}/complete", {
        "workerId": worker_id,
        "variables": variables or {},
    })


def fail(task_id: str, worker_id: str, message: str, details: str = "",
         retries: int = 0, retry_timeout_ms: int = 0) -> None:
    """Report a failure.

    retries=0 makes the engine raise an INCIDENT rather than retrying silently.
    That is the intended behaviour for unconfigured integrations — see README.
    """
    post(f"/external-task/{task_id}/failure", {
        "workerId": worker_id,
        "errorMessage": message[:666],
        "errorDetails": details[:4000],
        "retries": retries,
        "retryTimeout": retry_timeout_ms,
    })


# --- runtime queries (used by the mirror) ------------------------------------

def process_instances(definition_key: str) -> list[dict]:
    return get("/process-instance", {"processDefinitionKey": definition_key}) or []


def instance_variables(instance_id: str) -> dict:
    return decode_vars(get(f"/process-instance/{instance_id}/variables",
                           {"deserializeValues": "false"}))


def active_activity_ids(instance_id: str) -> list[str]:
    tree = get(f"/process-instance/{instance_id}/activity-instances")
    found: list[str] = []

    def walk(node: dict) -> None:
        if node.get("activityId"):
            found.append(node["activityId"])
        for child in node.get("childActivityInstances", []) or []:
            walk(child)
        for child in node.get("childTransitionInstances", []) or []:
            if child.get("activityId"):
                found.append(child["activityId"])

    if tree:
        walk(tree)
    return found


def open_tasks(instance_id: str) -> list[dict]:
    return get("/task", {"processInstanceId": instance_id}) or []


def incident_count(instance_id: str) -> int:
    result = get("/incident/count", {"processInstanceId": instance_id})
    return (result or {}).get("count", 0)


def start_instance(definition_key: str, business_key: str, variables: dict) -> dict:
    return post(f"/process-definition/key/{definition_key}/start", {
        "businessKey": business_key,
        "variables": variables,
    })
