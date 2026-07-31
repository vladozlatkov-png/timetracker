"""External task worker.

Long-polls Operaton for the topics in handlers.HANDLERS and executes them.

Why external tasks rather than embedded Java delegates: the audit work already
lives in the Claude skills stack and n8n. Keeping the engine on the other side
of a fetch-and-lock boundary means the orchestrator never needs to host that
code, and a worker crash leaves the engagement resumable rather than corrupt.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
import traceback

import operaton_client as engine
from handlers import HANDLERS, NotConfigured

WORKER_ID = os.environ.get("WORKER_ID", "external-tasks-1")
MAX_TASKS = int(os.environ.get("MAX_TASKS", "5"))
LOCK_MS = int(os.environ.get("LOCK_DURATION_MS", "120000"))
LONG_POLL_MS = int(os.environ.get("LONG_POLL_MS", "20000"))

# Transient failures get a few retries with backoff; NotConfigured gets none.
TRANSIENT_RETRIES = int(os.environ.get("TRANSIENT_RETRIES", "3"))
TRANSIENT_RETRY_TIMEOUT_MS = int(os.environ.get("TRANSIENT_RETRY_TIMEOUT_MS", "60000"))

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)
log = logging.getLogger("external-tasks")

_running = True


def _stop(signum, _frame):
    global _running
    log.info("signal %s received, finishing current batch then exiting", signum)
    _running = False


def handle(task: dict) -> None:
    topic = task["topicName"]
    task_id = task["id"]
    handler = HANDLERS[topic]

    try:
        result = handler(task) or {}
    except NotConfigured as exc:
        # Deliberate: no retries, so this surfaces as an incident in Cockpit.
        log.error("[%s] not configured: %s", topic, exc)
        engine.fail(task_id, WORKER_ID, f"{topic}: not configured", str(exc), retries=0)
        return
    except Exception as exc:  # noqa: BLE001 — worker must survive any handler
        retries = task.get("retries")
        remaining = TRANSIENT_RETRIES if retries is None else max(retries - 1, 0)
        log.exception("[%s] failed, %s retries left", topic, remaining)
        engine.fail(
            task_id, WORKER_ID, f"{topic}: {exc}", traceback.format_exc(),
            retries=remaining, retry_timeout_ms=TRANSIENT_RETRY_TIMEOUT_MS,
        )
        return

    # Handlers may return pre-encoded variables under "__raw__" when they need
    # a specific engine type (e.g. a java.util.ArrayList for multi-instance).
    raw = result.pop("__raw__", {})
    variables = {**engine.encode_vars(result), **raw}
    engine.complete(task_id, WORKER_ID, variables)
    log.info("[%s] completed task %s", topic, task_id)


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    topics = sorted(HANDLERS)
    log.info("worker %s polling %s at %s", WORKER_ID, topics, engine.OPERATON_URL)

    backoff = 1
    while _running:
        try:
            tasks = engine.fetch_and_lock(WORKER_ID, topics, MAX_TASKS, LOCK_MS, LONG_POLL_MS)
            backoff = 1
        except Exception as exc:  # noqa: BLE001 — engine may not be up yet
            log.warning("fetchAndLock failed (%s); retrying in %ss", exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue

        for task in tasks:
            if not _running:
                break
            handle(task)

    log.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
