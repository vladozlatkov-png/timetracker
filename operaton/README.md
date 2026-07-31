# Audit orchestrator — Operaton

BPMN process control for statutory audit engagements, sitting alongside the
existing Audit OS backbone.

**Scope:** Operaton owns phase transitions, human tasks, timers, and incidents.
The Postgres `workflow.*` schema stays the system of record for audit content.
The reasoning, the alternatives, and the rollout plan are in
[`docs/architecture.md`](docs/architecture.md) — read that first.

**Resuming in a new session?** Start with
[`docs/context.md`](docs/context.md) — the standing picture (estate map, live
engagements, open questions, environment gotchas) — then the dated log in
[`docs/sessions/`](docs/sessions/) for what happened and why. There is no
chat-history search in this environment; those files are how continuity works.

> **Status: not yet run against a live engine.** The models and code are
> statically validated and the database half is verified (see
> [Verification](#verification)), but nothing here has been executed against a
> running Operaton instance — the container image could not be pulled in the
> environment where this was written. Treat the first `make up && make deploy`
> as the real smoke test.

## Layout

```
bpmn/statutory-audit.bpmn   engagement lifecycle — phases, gates, approvals, timers
bpmn/audit-step.bpmn        one programme step; called multi-instance by the parent
sql/001_bridge_schema.sql   orchestrator.* bridge schema (applies to the Audit OS DB)
workers/external_tasks.py   fetch-and-lock worker for the five service topics
workers/mirror.py           one-way projection of engine state into orchestrator.*
scripts/deploy_bpmn.sh      deploy models to the engine
scripts/start_engagement.sh start one engagement instance
scripts/validate_bpmn.py    pre-deploy model checks
```

## Quick start

```bash
cp .env.example .env          # fill in ENGINE_DB_PASSWORD and AUDIT_OS_DSN
make up                       # engine + engine database
make migrate                  # bridge schema -> Audit OS database
make deploy                   # BPMN models -> engine
make workers                  # external-task + mirror workers
```

Cockpit `http://localhost:8080/operaton/app/cockpit/` (`demo`/`demo`),
Tasklist `http://localhost:8080/operaton/app/tasklist/`.

Start an engagement:

```bash
./scripts/start_engagement.sh EV-2026-CIC CIC "КОМПАНИЯ ЗА МЕЖДУНАРОДНИ КОНГРЕСИ ЕООД" 2025 2026-09-15
```

The last argument is the deadline *warning* date, which arms the non-interrupting
event sub-process. Set it before the contractual delivery date, not on it.

## The one rule

**The 31-step audit programme is not in the BPMN.** The models carry the
phase/gate skeleton; the step list is data, read from `orchestrator.v_steps` and
handed to a multi-instance call activity.

Adding a step is an `INSERT`. It is not a redeploy, and it never migrates an
engagement that is already in fieldwork. Putting the programme into the diagram
would reverse both of those properties — do not do it.

## Fail loudly

Every external-task handler raises an **incident** when its integration is not
configured. It never completes with a fabricated success.

This is deliberate and it matters most for `sanctions-check`: a handler that
defaulted to `sanctionsClear=true` would pass an engagement through acceptance
with no screening performed *and no trace that it was skipped*. An incident in
Cockpit is a visible, blocking, auditable "this did not run".

If you hit one of these incidents, configure the endpoint. Do not stub a
positive response.

| Topic | Requires | On failure |
|---|---|---|
| `sanctions-check` | `SANCTIONS_API_URL` | incident, 0 retries |
| `load-step-registry` | `AUDIT_OS_DSN` | incident, 0 retries |
| `run-audit-step` | `AUDIT_STEP_DISPATCH_URL` | incident, 0 retries |
| `pbc-chase` | `PBC_CHASE_WEBHOOK` | incident, 0 retries |
| `issue-report` | `ISSUE_REPORT_WEBHOOK` | incident, 0 retries |

Transient errors (network, 5xx) are different: those retry with backoff before
raising an incident.

## The mirror

`workers/mirror.py` projects engine state into `orchestrator.process_state`
every 60s. One-way and derived, matching the contract the Notion cards already
carry ("mirrored one-way — do not edit here").

It renders `blocked_reason` in the existing card format, so the current Notion
sync needs no change:

```
G-WP-CONCLUDED open, G-EVIDENCE-LOCK open · next: fw-je, fw-rp
```

Gate predicates and the activity→status map live at the top of `mirror.py`.
Keep the gate codes aligned with the ones already on the cards.

## Security

The Operaton REST API is **unauthenticated by default**, and the webapps ship
with the `demo`/`demo` account. The compose file binds port 8080 to loopback
for that reason.

Before this is reachable by anyone else: change the demo credentials, and put
the REST API behind either Tailscale or an authenticating reverse proxy. Do not
just flip `OPERATON_BIND` to `0.0.0.0`.

## Notes on the BPMN files

- Extension elements use the current `operaton:` namespace
  (`http://operaton.org/schema/1.0/bpmn`). The engine also accepts the legacy
  `camunda:` namespace, so a diagram round-tripped through Camunda Modeler will
  still deploy — expect the prefix to change if you edit it there.
- Redeploying creates a **new version**. Running instances stay on the version
  they started with, which is what protects an engagement mid-fieldwork from a
  methodology change.
- `historyTimeToLive` is `P10Y` on both processes, for engagement file
  retention. Confirm against the firm's actual retention policy before this
  goes near a real engagement.

## Verification

What has been checked, and how:

- **BPMN** — both models parse; every flow node has a `BPMNShape` and every
  sequence flow a `BPMNEdge` (a missing shape renders as a broken diagram in
  Cockpit, which defeats the point); all `sourceRef`/`targetRef` and
  `attachedToRef` resolve; conditional exclusive gateways all have a default
  flow. Run `make validate`.
- **Bridge schema** — applied against a real PostgreSQL 16 server, then applied
  a second time to confirm idempotency.
- **Mirror logic** — `derive_status`, gate predicates, and `render_blocked_reason`
  unit-checked; `step_counts` and `pending_steps` run against a live database
  with seeded step results. Output was confirmed byte-identical to the format
  on the live engagement cards.
- **Variable encoding** — `json_list_var` produces the `java.util.ArrayList`
  shape the multi-instance `collection` expression needs.
- **Handlers** — an unconfigured `sanctions-check` raises `NotConfigured`
  rather than returning a pass.

Not checked: anything requiring a running engine — deployment, form rendering,
timer firing, multi-instance expansion, external-task fetch-and-lock.
