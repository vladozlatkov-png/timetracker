# ADR 001 — Operaton owns process control, `workflow.*` keeps audit content

Status: **proposed** · 2026-07-31

## Context

Audit OS backbone slice 2 is live. Postgres `workflow.*` is the system of
record; the Notion engagement cards are a read-only one-way mirror. As of
2026-07-31 it is tracking real engagements — КУМЕР at 24/31 steps, Global
Exchange at 11/31, both in fieldwork — with a content-hashed step registry
(`f19302d`), six gate codes, and a derived `Blocked Reason` string.

In other words a workflow engine already exists and works. The question is not
whether to have one, but whether the parts it does *not* do are worth adding a
BPMN engine for.

What `workflow.*` does not give:

- **Human work items as first-class objects.** Pending human work is a `next:`
  string on a status field. There is no inbox, no assignee, no claim, no
  per-person queue.
- **Timers.** PBC chasing and the contractual delivery deadline (e.g.
  30.09.2026 for GLX) have no scheduled escalation.
- **A model a person can look at.** The lifecycle is implied by code and data,
  not shown.
- **Incidents as a queue.** "Blocked" is a computed string, not a work list —
  Phase 5 of the old roadmap ("Blocked Item Queue") is still unbuilt.

## Decision

Adopt Operaton, scoped narrowly.

**Operaton owns process control:** phase transitions, human tasks and their
forms, timers and escalation, incidents, and the execution history.

**`workflow.*` remains the system of record for audit content:** the step
registry, evidence, materiality, gate satisfaction, and anything with a
retention obligation.

The two are joined by a new `orchestrator` schema in the Audit OS database.
Nothing in `workflow.*` is created, altered, or dropped.

### Consequences of the split

- The engine database is separate from the Audit OS database. Engine tables are
  an implementation detail of Operaton and must not sit beside audit records.
- The mirror is one-way and derived — the same contract the Notion cards
  already carry. It renders `blocked_reason` in the existing card format
  (`G-X open, G-Y open · next: a, b`) so the Notion sync needs no change.
- Two stores means a consistency window. Accepted: the mirror is idempotent and
  converges every pass, and no decision is made from the mirror — only read
  from it.

## The rule that matters most

**The 31-step audit programme is not in the BPMN.**

BPMN models the phase/gate skeleton: six phases, six gates, the human
approvals, the timers. The programme steps stay data-driven, delivered to a
multi-instance call activity as a collection read from `orchestrator.v_steps`.

The reason is operational, not aesthetic. A 31-task diagram means every
methodology change is a process redeploy plus an instance migration on live
engagements. With the step list as data, adding `fw-wp:inventory` mid-season is
an `INSERT` — no redeploy, no migration, no risk to an engagement in fieldwork.

The corollary: `audit-step.bpmn` is a separate process definition called by the
parent, so the step lifecycle can version independently of the engagement
lifecycle.

## Alternatives considered

**Build a read UI over `workflow.*` instead.** Materially cheaper, and it
answers "I want to see status" completely. Rejected only because it answers
none of the other three gaps (task inbox, timers, incident queue). If those
turn out not to matter in practice, this is the better call — and the honest
test is the pilot.

**Camunda 7 CE.** [End of life October 2025](https://operaton.org/2025/04/29/what-we-learned-from-taking-over-camunda-7-ce/).
Not an option for new work.

**Camunda 8 / Zeebe.** Different architecture, and the community offering is
materially more restricted. The gain over Operaton does not justify it here.

**n8n for human tasks.** n8n is an automation runtime, not a state store. It
has no task inbox, no per-instance state a partner can inspect, and no
incident model. It stays where it is — as an external-task worker.

## Risks

- **Operaton project maturity.** The engine is a decade-old codebase; the
  maintaining organisation is roughly eighteen months old. Mitigation: Apache
  2.0, and the Camunda 7 REST API and DB schema are compatible, so the exit
  path is a fork rather than a rewrite.
- **A JVM service in a Python/Postgres/Frappe estate.** Real added operational
  surface. Mitigation: runs as a container, no application code inside it —
  all work happens in external-task workers.
- **Migration of in-flight engagements.** Do not. Engagements currently in
  fieldwork against a September deadline stay on the existing backbone until
  they close.

## Rollout

1. Apply `sql/001_bridge_schema.sql`; repoint `orchestrator.v_steps` at the
   real registry.
2. Deploy the models, wire the four integration endpoints.
3. Pilot on **one not-yet-started** engagement from the July batch — CIC or
   ДИВЕРТИМЕНТО. Never on КУМЕР or GLX.
4. Run both systems in parallel for that engagement through one full phase
   transition before deciding anything.
