-- =============================================================================
-- Orchestration bridge — Operaton <-> Audit OS
--
-- Runs against the EXISTING Audit OS Postgres (the one holding workflow.*),
-- NOT against the engine database.
--
-- Everything lives in its own `orchestrator` schema. Nothing in `workflow.*`
-- is created, altered or dropped here: the existing backbone stays the record
-- of audit content, and this schema only records process control state.
-- =============================================================================

create schema if not exists orchestrator;

comment on schema orchestrator is
  'Operaton process-control state. workflow.* remains the system of record for '
  'audit content (steps, evidence, gate satisfaction). One-way: Operaton writes '
  'here, nothing here writes back into the engine.';

-- -----------------------------------------------------------------------------
-- 1. Engagement <-> process instance correlation
-- -----------------------------------------------------------------------------
create table if not exists orchestrator.engagement_process (
    engagement_id        text primary key,
    process_instance_id  text not null unique,
    business_key         text,
    process_definition   text not null default 'statutory-audit',
    started_at           timestamptz not null default now(),
    ended_at             timestamptz
);

-- -----------------------------------------------------------------------------
-- 2. Mirrored state snapshot, refreshed by workers/mirror.py
--
-- `blocked_reason` is rendered in the exact format the Notion engagement cards
-- already use, so the existing one-way Notion mirror keeps working unchanged:
--     "G-WP-CONCLUDED open, G-EVIDENCE-LOCK open · next: fw-je, fw-rp"
-- -----------------------------------------------------------------------------
create table if not exists orchestrator.process_state (
    engagement_id      text primary key
                         references orchestrator.engagement_process(engagement_id)
                         on delete cascade,
    status             text not null,
    gates_open         text[] not null default '{}',
    gates_closed       text[] not null default '{}',
    next_steps         text[] not null default '{}',
    open_human_tasks   jsonb  not null default '[]'::jsonb,
    incident_count     integer not null default 0,
    steps_done         integer,
    steps_total        integer,
    blocked_reason     text,
    derived_at         timestamptz not null default now()
);

-- -----------------------------------------------------------------------------
-- 3. Per-step outcomes written by the run-audit-step handler
-- -----------------------------------------------------------------------------
create table if not exists orchestrator.step_result (
    id                  bigserial primary key,
    engagement_id       text not null,
    step_key            text not null,
    process_instance_id text,
    outcome             text not null check (outcome in ('completed', 'failed', 'skipped')),
    detail              jsonb not null default '{}'::jsonb,
    recorded_at         timestamptz not null default now()
);

create index if not exists step_result_engagement_idx
    on orchestrator.step_result (engagement_id, step_key, recorded_at desc);

-- -----------------------------------------------------------------------------
-- 4. THE CONTRACT: the step list the engine multi-instances over.
--
--    >>> REPOINT THIS VIEW AT THE REAL workflow.* REGISTRY BEFORE PILOTING. <<<
--
-- The engine only ever reads this view. It must return, per engagement:
--     step_key         text     e.g. 'fw-wp:revenue'
--     step_name        text     human label shown in Cockpit / Tasklist
--     phase            text     acceptance | planning | fieldwork | completion
--     requires_review  boolean  drives the review branch in audit-step.bpmn
--     sort_order       integer
--
-- Replacing the body with a select over the real registry is the ONLY change
-- needed here — no BPMN redeploy, no instance migration.
-- -----------------------------------------------------------------------------
create table if not exists orchestrator.step_seed (
    step_key        text primary key,
    step_name       text not null,
    phase           text not null,
    requires_review boolean not null default false,
    sort_order      integer not null
);

-- Seeded from the step keys observed on live engagement cards (registry f19302d,
-- 2026-07-31). Placeholder data for the pilot only — the real registry is the
-- authority and this table should be dropped once the view is repointed.
insert into orchestrator.step_seed (step_key, step_name, phase, requires_review, sort_order) values
    ('acc-memo',              'Acceptance memo',                'acceptance',  true,  10),
    ('pln-tb2ls',             'Trial balance to lead schedules', 'planning',   false, 20),
    ('fw-pbc-chase',          'PBC chase',                      'fieldwork',   false, 30),
    ('fw-wp:revenue',         'Workpaper — revenue',            'fieldwork',   true,  40),
    ('fw-wp:receivables',     'Workpaper — receivables',        'fieldwork',   true,  50),
    ('fw-wp:ppe',             'Workpaper — PPE',                'fieldwork',   true,  60),
    ('fw-wp:related_parties', 'Workpaper — related parties',    'fieldwork',   true,  70),
    ('fw-wp:expenses',        'Workpaper — expenses',           'fieldwork',   true,  80),
    ('fw-je',                 'Journal entry testing',          'fieldwork',   true,  90),
    ('fw-rp',                 'Related party procedures',       'fieldwork',   true, 100),
    ('fw-est',                'Accounting estimates',           'fieldwork',   true, 110)
on conflict (step_key) do nothing;

create or replace view orchestrator.v_steps as
select
    step_key,
    step_name,
    phase,
    requires_review,
    sort_order
from orchestrator.step_seed;

comment on view orchestrator.v_steps is
  'Contract read by the load-step-registry external task worker. Repoint at the '
  'real workflow.* step registry; the column shape is the interface.';
