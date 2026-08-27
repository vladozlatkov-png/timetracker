# Build prompt — Realization

> Hand this whole file to a coding agent as the task brief. It is self-contained: it assumes no
> knowledge of the owner, the repo, or the surrounding infrastructure.

---

## 1. Who this is for

Vladimir Zlatkov, a registered statutory auditor in Bulgaria, running **Easy Ventures EOOD** from
Bankya. He works alone with contractors, on fixed-fee statutory audit engagements. He is technical:
he runs his own Proxmox host, a Docker fleet, n8n, Grafana, Metabase and Home Assistant behind
Tailscale, and he writes and reads code. Timezone **Europe/Sofia**. He writes in English and
Bulgarian; client names appear in both scripts.

Ship things that are small, finished and used daily. He has a documented tendency to start
seven-phase roadmaps and finish phase one — so the brief below is deliberately six steps, each of
which is independently useful the day it lands.

## 2. The problem

Two systems already know that billable hours matter. Neither one has any hours in it.

- The **time tracker PWA** in this repo has a `Billing` activity whose sub-activities are literally
  `Audit work` and `EV`. It records *that* he worked. It has no client dimension, so it cannot say
  *who he worked for*.
- His **Notion "Audit OS" workspace** has a Tasks database with `Estimated Hours`, `Actual Hours`,
  a `Billable` checkbox, and relations to Engagement and Project. Correct schema, unused: at last
  count **43 open tasks, 134 estimated hours, and 15 actual hours ever recorded**.
- His **engagement fees are fixed** and already exist (a `Договори_одит_2024` contracts sheet in
  Google Drive). There is nothing to divide them by.

So the number he cannot currently produce — and the one that changes what he charges at renewal —
is **realization**: fee ÷ hours actually worked, per engagement.

## 3. What to build

**Realization** — engagement-aware time tracking with a client-profitability read-out.

Keep the tracker he already uses. Add **one field** (what the time is against), **one sync** (to the
Postgres he already runs), and **one report** (realization per engagement). Everything else in the
app stays as it is, because the rest of it works.

Two things follow from how he actually works, and they are requirements, not nice-to-haves:

- **The record will be wrong, continuously.** Buttons get missed, timers get started late, whole
  sessions happen away from the phone. An instrument that only records perfect input records
  nothing. Correction and backfill are core paths, not an admin screen.
- **Not all working time belongs to a client.** He does his own development and internal work
  during normal working hours, and it currently has nowhere to go. It needs a first-class home, or
  it will be logged as a client's time or not logged at all — and both corrupt the number.

Four deliverables, in this order:

1. **The main schema** — Postgres, the system of record.
2. **The app** — the existing PWA extended, plus the realization view.
3. **Correction, backfill and reconciliation** — the paths that keep the data honest.
4. **One-touch entry points** — iPhone and iPad: Home Screen deep links, Shortcuts, widgets, Siri.

### The two numbers

Because internal work is now tracked, there are two headline figures, not one, and they answer
different questions:

- **Realization** — fee ÷ hours worked, per client engagement. *Am I charging enough?*
- **Utilization** — billable hours ÷ total working hours. *How much of my working life reaches an
  invoice at all?*

Utilization is the one that will be uncomfortable, and it is only computable because internal work
is being recorded. Do not hide it.

---

## 4. Current state of the repo

Single-file PWA, no build step, no dependencies, no framework. Five files:

| File | Purpose |
|---|---|
| `index.html` | The entire app — markup, CSS and JS inline |
| `manifest.json` | PWA metadata |
| `sw.js` | Service worker, offline cache |
| `icon-192.svg`, `icon-512.svg` | Icons |

Interaction model: **single tap** on an activity starts its timer immediately; **hold 0.6 s** opens
the sub-activity picker. Three tabs: `Track`, `Log`, `Export`.

Activities are declared in one array near the top of the script block:

```js
const ACTS = [
  { id:'rest',    label:'Rest',    icon:'🛋', color:'#1D9E75', subs:['Sleep','Nap','Rest','Other'] },
  { id:'eat',     label:'Eat',     icon:'🍽', color:'#EF9F27', subs:['Cook','Breakfast','Lunch','Snack','Dinner','Dine out'] },
  { id:'care',    label:'Care',    icon:'🪥', color:'#D4537E', subs:['Personal','Custom'] },
  { id:'billing', label:'Billing', icon:'💳', color:'#7F77DD', subs:['Audit work','EV','Custom'] },
  { id:'work',    label:'Work',    icon:'🔨', color:'#378ADD', subs:['House','Garden','Custom'] },
  { id:'train',   label:'Train',   icon:'🏊', color:'#D85A30', subs:['Swimming','Tennis','Yoga','Weights','Run','Bike','Custom'] },
  { id:'study',   label:'Study',   icon:'📚', color:'#639922', subs:['Language','AI','IDES','Custom'] },
  { id:'pets',    label:'Pets',    icon:'🐾', color:'#BA7517', subs:['Food','Train','Play','Custom'] }
];
```

Entries live in `localStorage` under key `tt_v1`, newest first, shaped:

```js
{ id, activity, label, sub, start, end, duration, color }   // start/end/duration in ms
```

Export writes day / week / month CSV client-side. There is no server, no account, no sync.

## 5. Surrounding infrastructure — use it, do not replace it

All of this is already running and must not be re-hosted:

- **Ubuntu VM** on Proxmox, ~15 Docker containers, reachable over **Tailscale**; public ingress via
  **cloudflared** at `automation.easyventures.eu`.
- **`postgres_audit`** — Postgres container. This is where hours go.
- **n8n** — the integration layer. Existing workflows already talk to Postgres and Telegram; there
  is a `bot.skills` table and a working Telegram bot ("Marty Party") to copy patterns from.
- **Grafana** and **Metabase** — already pointed at that Postgres. Prefer these over writing chart
  code, unless the view belongs inside the PWA.
- **Notion** — the "Audit OS" workspace, the current system of record for engagements and tasks.
- Bot lane rule he set himself and wants respected: **Aegis** handles business data (Notion,
  Postgres, audit work); **Marty Party** handles the house (Home Assistant, LAN, devices). This
  project is squarely Aegis. Marty must not touch it.

### Notion identifiers

| Database | Data source id |
|---|---|
| Tasks | `c1dec314-ae83-43e8-ab9f-db98a3c6c6ad` |
| Engagements | `9a26c585-88e5-434d-86e1-7804e1fe2121` |
| Projects | `cf24a3e6-5365-4b08-8e9e-5ef89ae3bc1b` |
| Documents | `4c3439de-0a3a-4e7e-a137-12356f58ac21` |

Tasks schema, as it exists: `Task ID` (text), `Task Name` (title), `Status` (`todo` /
`in_progress` / `done`), `Task Type` (`analysis` / `testing` / `review` / `admin` / `meeting` /
`request`), `Owner` (person), `Due Date` (date), `Estimated Hours` (number), `Actual Hours`
(number), `Billable` (checkbox), plus relations to Engagement, Project and Documents.

Live 2025–26 engagements to seed with: **Scorpio Oil Transport OOD**, **Global Exchange OOD**,
**Кумер ООД**, **Фешън Айкон ООД**, **МБАЛ Самоков ЕООД**, **Би Ту Би ЕООД**.

---

## 6. Deliverable 1 — the main schema

Design the Postgres schema in `postgres_audit`, in its own schema namespace (suggest `tt`). Below
is a **proposed starting point, not a specification** — refine it, but keep the properties called
out after it.

The central modelling decision: **time is booked against a *stream*, not against a client.** A
stream is anything work can belong to. Some streams are client engagements and carry a fee; some
are his own internal projects and carry none. This is what lets internal development be recorded
honestly instead of being squeezed into a client code or left untracked.

```sql
create schema if not exists tt;

-- Clients mirror Notion; Notion stays the editing surface, Postgres the truth for hours.
create table tt.client (
  id             uuid primary key default gen_random_uuid(),
  name           text not null,
  name_local     text,                        -- Cyrillic legal name where it differs
  notion_page_id text unique,
  active         boolean not null default true,
  created_at     timestamptz not null default now()
);

-- Every bookable thing: client engagements, internal projects, admin buckets.
create table tt.stream (
  id             uuid primary key default gen_random_uuid(),
  kind           text not null
                 check (kind in ('client','internal','admin')),
  client_id      uuid references tt.client(id),   -- required for kind='client', else NULL
  name           text not null,              -- 'Statutory Audit FY2025' | 'Realization app'
  code           text unique not null,       -- short tap-target label: 'SCORPIO-25', 'DEV-REAL'
  notion_page_id text unique,
  fiscal_year    int,
  fee_amount     numeric(12,2),              -- client streams only, from Договори_одит_2024
  fee_currency   text not null default 'EUR', -- single-currency system; see note below
  billing_model  text not null default 'fixed'
                 check (billing_model in ('fixed','tm')),
  budget_hours   numeric(8,2),               -- his own estimate, for burn
  billable_default boolean not null default false,
  status         text not null default 'active'
                 check (status in ('active','blocked','complete','archived')),
  started_on     date,
  due_on         date,
  sort_hint      timestamptz,                -- last touched, for ordering the picker
  created_at     timestamptz not null default now(),
  constraint client_streams_have_a_client
    check ((kind = 'client') = (client_id is not null)),
  constraint only_client_streams_have_fees
    check (kind = 'client' or fee_amount is null)
);

-- The immutable fact table. One row per booked interval; corrections are new rows.
create table tt.time_entry (
  id             uuid primary key,           -- generated CLIENT-side; the idempotency key
  device_id      text not null,              -- which phone/tablet/browser produced it
  activity       text not null,              -- 'billing', 'study', 'train', ...
  sub            text,                       -- sub-activity, unchanged from today
  stream_id      uuid references tt.stream(id),   -- NULL for personal activities
  task_notion_id text,                       -- optional, when booked to a specific task
  billable       boolean not null default false,
  started_at     timestamptz not null,
  ended_at       timestamptz not null,
  duration_s     int generated always as
                   (extract(epoch from (ended_at - started_at))::int) stored,
  note           text,

  -- how this row came to exist, and how much it can be trusted
  source         text not null default 'pwa'
                 check (source in ('pwa','shortcut','manual','backfill','import')),
  confidence     text not null default 'timed'
                 check (confidence in ('timed','adjusted','reconstructed')),

  -- correction chain: a row is current unless something supersedes it
  supersedes_id  uuid unique references tt.time_entry(id),
  void           boolean not null default false,   -- 'this never happened'
  reason         text,                             -- required when correcting or voiding

  entered_at     timestamptz not null default now(),  -- when the row was written
  synced_at      timestamptz not null default now(),
  constraint sane_interval check (ended_at > started_at),
  constraint corrections_explain_themselves
    check (supersedes_id is null and not void or reason is not null)
);

-- Current truth = rows nothing supersedes, minus voids.
create view tt.entry_current as
select e.* from tt.time_entry e
where not exists (select 1 from tt.time_entry s where s.supersedes_id = e.id)
  and not e.void;

create index on tt.time_entry (stream_id, started_at desc);
create index on tt.time_entry (activity, started_at desc);
create index on tt.time_entry (started_at desc);

-- Rates, so realization survives a fee renegotiation without rewriting history.
create table tt.rate (
  id            uuid primary key default gen_random_uuid(),
  stream_id     uuid not null references tt.stream(id),
  target_hourly numeric(10,2) not null,       -- what an hour SHOULD earn
  currency      text not null default 'EUR',
  valid_from    date not null,
  valid_to      date
);
```

Plus the two views that are the actual product:

```sql
-- Realization: client streams only. Am I charging enough?
create view tt.realization as
select s.id, s.code, c.name as client, s.fee_amount, s.fee_currency,
       round(sum(t.duration_s)/3600.0, 2)                                   as hours,
       s.budget_hours,
       round(sum(t.duration_s)/3600.0 / nullif(s.budget_hours,0) * 100, 1)  as burn_pct,
       round(s.fee_amount / nullif(sum(t.duration_s)/3600.0, 0), 2)         as effective_hourly,
       round(100.0 * sum(t.duration_s) filter (where t.confidence <> 'timed')
             / nullif(sum(t.duration_s),0), 1)                              as reconstructed_pct
from tt.stream s
join tt.client c on c.id = s.client_id
left join tt.entry_current t on t.stream_id = s.id
where s.kind = 'client'
group by s.id, c.name;

-- Utilization: all working time. How much of it reaches an invoice?
create view tt.utilization as
select date_trunc('month', t.started_at at time zone 'Europe/Sofia') as month,
       round(sum(t.duration_s) filter (where t.billable)/3600.0, 2)  as billable_h,
       round(sum(t.duration_s) filter (where s.kind = 'internal')/3600.0, 2) as internal_h,
       round(sum(t.duration_s) filter (where s.kind = 'admin')/3600.0, 2)    as admin_h,
       round(sum(t.duration_s)/3600.0, 2)                            as total_h,
       round(100.0 * sum(t.duration_s) filter (where t.billable)
             / nullif(sum(t.duration_s),0), 1)                       as utilization_pct
from tt.entry_current t
left join tt.stream s on s.id = t.stream_id
where t.stream_id is not null            -- working time only; Rest/Train/Pets excluded
group by 1 order by 1 desc;
```

**Properties the schema must have, however you shape it:**

- **Client-generated UUID primary key on `time_entry`.** The phone is offline-first; the same entry
  will be POSTed more than once. `on conflict (id) do nothing` must make retries free.
- **Immutable rows, mutable truth.** No `UPDATE` on a synced entry, ever. An edit inserts a
  replacement row carrying `supersedes_id`; a deletion inserts a `void` row. Both require a
  `reason`. Current state is the `tt.entry_current` view, never the base table. This is exactly how
  audit working papers handle corrections, and it is why editing does *not* weaken the record — a
  corrected timesheet stays defensible in a client file because the original and the reason are
  both still there. The `unique` on `supersedes_id` stops one row being corrected into two.
- **`confidence` is not decoration.** `timed` means a real start and stop. `adjusted` means a timed
  entry whose boundaries were corrected. `reconstructed` means it was written from memory after the
  fact. Every downstream report must be able to show the split, and the timesheet export must show
  it by default. **A reconstructed billable hour that looks identical to a timed one is exactly the
  failure mode to avoid.**
- **`timestamptz` everywhere**, stored UTC, rendered Europe/Sofia. He observes DST; a local-naive
  timestamp will silently corrupt an hour twice a year — and backfill entries, which are typed in
  local wall-clock time, are where that bug will actually bite.
- **Personal activities keep working.** `stream_id` is nullable. Rest, Train, Study and Pets sync
  too — they are the control group, and the Study Cockpit (the next project) will reuse this exact
  table with a subject stream rather than a new one.
- **This is a single-currency system. Every fee is in EUR.** All contracts are denominated in
  euro, the FY2025 audits included, regardless of when they were signed. There is **no BGN
  anywhere**, and therefore no conversion logic, no dual display, and no FX table to maintain.
  The `fee_currency` column is retained as a one-line hedge against a future non-EUR client — it is
  not a feature. Do not build currency handling on top of it.
- **Two billing models in the schema, one in the data.** Every engagement today is fixed-fee, so
  realization is always fee ÷ hours for now. Time-and-materials engagements are expected *after*
  this system exists — the column goes in now so that arrival is a config change rather than a
  migration, but the T&M variance view is deferred (see §13). Seed every stream as `fixed`.
- **Billable is a per-entry decision, including on internal streams.** Internal work is
  occasionally chargeable, so `kind='internal'` must not hard-force `billable=false`.
  `billable_default` stays false for internal streams and the flag is an explicit per-session
  toggle — never sticky between sessions, and never inherited silently from the last entry. See
  §7.1 for what the UI owes this.
- Provide **forward migration SQL** and a documented rollback. Do not use an ORM's auto-migrate.

### Seeding streams

Client streams: the six live engagements listed in §5. Internal streams to create on day one, so
there is somewhere for the work to go — refine the list with the owner:

| Code | Kind | Name |
|---|---|---|
| `DEV-AUDITOS` | internal | Audit OS / ERPNext |
| `DEV-REAL` | internal | Realization app |
| `DEV-HOMELAB` | internal | Home lab & infrastructure |
| `EV-ADMIN` | admin | Easy Ventures administration, banking, filings |
| `BD` | admin | Business development, leads, proposals |

`EV` currently exists as a sub-activity under Billing. Migrate it to `EV-ADMIN` rather than leaving
two competing concepts.

## 7. Deliverable 2 — the app

### 7.1 Stream picker

Tapping `Billing` must offer live streams — most recently used first — instead of the current
generic sub list. Ordering comes from `sort_hint`; cache the list in `localStorage` so it is
available with no network. All other activities keep their existing sub-activity behaviour
untouched.

Group the picker by kind, with client engagements first and internal/admin streams below a divider.
Make the two visually distinguishable at a glance — an internal stream must never be mistaken for a
client one mid-tap. The `billable` flag on a new entry defaults from the stream's
`billable_default`, and the running-timer bar states plainly whether the current session is
billable.

Because internal work can occasionally be billable, the timer bar carries a **billable toggle**
that can be flipped mid-session — but it defaults to off for internal streams every time, never
remembering the last choice. Silently inheriting billability from a previous session is the exact
route to a false billable hour.

Keep the interaction he already has: **one tap starts the last-used stream immediately**, hold
opens the picker. Do not make him choose twice to start a timer.

### 7.2 Offline-first sync

Entries continue to be written to `localStorage` exactly as now. Add a queue that flushes to the
sync endpoint whenever the device has a route to the VM (typically Tailscale, sometimes the
cloudflared hostname). Requirements:

- Starting or stopping a timer must **never** await the network.
- Retries with backoff; the client UUID makes duplicate POSTs harmless.
- Show a small, honest sync state — pending count, last successful sync. No spinners that lie.
- Nothing is deleted locally until the server has acknowledged it.

Endpoint shape (adjust as you see fit, but keep it this small):

```
POST /api/entries        body: { device_id, entries: [ …time_entry… ] }   → { accepted: [ids] }
GET  /api/streams        → [ { id, code, name, kind, client, billable_default, sort_hint } ]
GET  /api/realization    → rows from tt.realization
GET  /api/utilization    → rows from tt.utilization
GET  /api/day/:date      → current entries for that local day, plus computed gaps
```

Corrections and backfills are **not** separate endpoints: they are ordinary entries POSTed to
`/api/entries` carrying `supersedes_id` / `void` / `reason`, so they queue, retry and dedupe
through the exact same offline path as a live timer. There is one write path.

Auth: a static bearer token in the device's local storage is acceptable **only** because the
endpoint is Tailscale-only. If it is ever exposed through cloudflared, put Cloudflare Access in
front of it. Do not build a login screen.

### 7.3 Notion write-back

An n8n workflow, both directions:

- **In:** engagements from Notion → `tt.stream` with `kind='client'` (upsert on `notion_page_id`).
  Internal and admin streams are managed in Postgres and do not exist in Notion.
- **Out:** hours per stream/task → Notion `Actual Hours` on the task rows that already have the
  field. Roll up on a schedule, not per entry; make it idempotent, since it will re-run.
- **Corrections must reach Notion.** A superseding or void entry marks its period dirty; the next
  roll-up recomputes that period from `tt.entry_current` rather than adding a delta. Recompute, do
  not increment — that is what makes the re-run safe.

Copy the credential and node patterns from the existing Marty_Party workflow in `workflows/`.

### 7.4 The realization view

The screen he opens weekly. Per fixed-fee client engagement: fee, hours to date, **effective hourly rate**, burn
against his own `budget_hours`, and a clear flag when an engagement crosses the point where it
stops being worth doing at that fee. Sort by effective hourly ascending — the worst deal first, on
purpose.

There are no time-and-materials engagements yet, so **do not build the T&M variance view now** —
there would be no data to test it against. Make `tt.realization` filter on
`billing_model = 'fixed'` so that when the first T&M stream appears it is excluded rather than
reported as a nonsense hourly rate. Building the variance view is a later, separate step.

All fees are EUR. Do not add currency selectors, conversion, or a currency column to any report.

Show `reconstructed_pct` alongside each engagement. An effective hourly rate computed from 80%
reconstructed time is a different claim from one computed from timed work, and the screen must say
so rather than presenting both as the same number.

Include utilization on the same surface — billable, internal and admin hours per month, and the
billable share. It is the counterpart question to realization and comes free from the same data.

Build it as a fourth tab in the PWA if it can be done in plain JS in keeping with the existing
file, or as a Metabase dashboard if that is materially faster. State which you chose and why.

### 7.5 Timesheet export

Per-engagement, per-period, in a form an audit file will accept — not a raw dump of eight activity
types. Keep the existing day/week/month CSV export working unchanged alongside it.

## 8. Deliverable 3 — correction, backfill and reconciliation

He has said plainly that missed pushes and late starts are continuous, not occasional. Treat that
as the operating condition. The goal is not a perfect record; it is a record whose imperfections are
**visible, correctable, and labelled**.

### 8.1 Edit an entry

The `Log` tab becomes editable. Tapping an entry opens it for correction: start time, end time,
activity, sub-activity, stream, billable flag, note. Also offer **split** (one long entry that was
really two) and **merge** (a session interrupted by a missed restart) — those two cover most of what
actually goes wrong with a tap-to-track timer.

Saving does not update the row. It writes a new entry with `supersedes_id` pointing at the original,
`confidence = 'adjusted'`, and a short reason. The original stays. The `Log` tab shows current
entries by default, with corrected ones carrying a discreet marker that reveals the prior version
and the reason on tap. Deleting is a `void` row, never a `DELETE`.

Editing must work fully offline — the correction queues like any other entry.

### 8.2 Add time that was never timed

A **quick add** path for work that happened away from the phone, off the grid, or before he thought
to press anything. Optimise it for entry from memory, which means duration-first, not clock-first:

- Pick the stream, then say **how long** ("2h", "45m", "1h30") and **roughly when** (defaults to
  today, with yesterday and a date picker one tap away).
- Derive `started_at` / `ended_at` from that, anchored to a sensible default block, and let him
  nudge the boundaries if it matters.
- Stamp `source = 'backfill'`, `confidence = 'reconstructed'`, and require the note field to be at
  least offered — a month later "3h Scorpio" with no note is nearly useless.
- Support backdating to any past date, but require an extra confirmation beyond about a week, and
  never silently accept a date in the future.

Multi-day backfill (returning from three days on a client site) should be possible without three
separate flows — a compact multi-row entry form on iPad is the right surface for that.

### 8.3 Daily reconciliation — the part that actually fixes it

An edit button treats the symptom. The prevention is making the gaps visible while he still
remembers what was in them.

Build a **Day** view: the local day as a timeline, entries in place, and the **unaccounted gaps**
between them called out with their duration. Tapping a gap opens the quick-add path pre-filled with
that gap's start, end and duration, so filling it is one tap plus a stream. Show a single honest
figure at the top: hours accounted for, hours unaccounted.

Gaps are computed against a configurable working window, so that sleep is not reported as a gap:

| Day | Window |
|---|---|
| Monday–Friday | **08:00–21:00** local |
| Saturday | **six working hours** — window defaults to 10:00–16:00, see §13 |
| Sunday | **none** — no gap detection at all |

Put these in one config object at the top of the script, not scattered through the gap logic. He
will change them.

**Any** entry counts as accounted time, not just working streams — lunch logged as Eat, or a nap
logged as Rest, closes a gap exactly as billable work does. The Day view reports time with *no
entry at all*, which is the only thing he can actually act on. A thirteen-hour weekday window works
precisely because Eat, Care and Rest already fill most of what is not work.

Add one **end-of-day nudge** — a notification or a Shortcuts automation — that opens the Day view
if unaccounted time exceeds a threshold. One per day, dismissible, never nagging. This is the single
highest-value thing in the whole deliverable: a gap filled at 19:00 the same evening is
`reconstructed` but accurate; the same gap filled next week is a guess.

### 8.4 Guardrails

These follow directly from *a false billable hour is worse than a missing one*:

- **Never auto-fill billable time.** Gaps may be *suggested* — including a suggestion inferred from
  the last stream used — but a billable entry is only ever created by an explicit confirmation.
- **Reconstructed time is always marked**, in the UI, in the timesheet export, and in the
  realization view (`reconstructed_pct`). It is never silently indistinguishable from timed work.
- **Overlaps are errors, not merges.** Two current entries covering the same interval must be
  surfaced for resolution, not silently reconciled. Enforce it on write and show it in the Day view.
- **Corrections re-roll-up.** Editing or voiding an entry that has already been pushed to Notion
  `Actual Hours` must mark the affected period dirty so the next n8n run recomputes it. A correction
  that never reaches Notion is worse than no correction.
- **Superseded and void rows are never deleted or purged.** They are the audit trail.
- **Reason is required** on every correction, void and backdated backfill. Keep it to one line; do
  not build a workflow around it.

## 9. Deliverable 4 — one-touch on iPhone and iPad

The goal is **starting the right timer in one physical action**, from a cold phone. Deliver all of
the following that survive contact with current iOS, and say plainly which ones did not:

1. **Deep-linked Home Screen icons.** Support `?start=<engagement-code>` in the PWA so a URL starts
   that engagement's timer on load and shows a confirmation, not a menu. Then one Safari
   "Add to Home Screen" bookmark per engagement gives a literal one-touch grid. Give each a
   distinguishable icon — generate per-engagement SVG icons from the existing `icon-512.svg`.
2. **Shortcuts that hit the API directly**, so they work without opening the app: `Start <stream>`,
   `Stop timer`, `What am I tracking?`, `Hours on <stream> this month`. Use *Get Contents of URL*
   against the Tailscale endpoint. Provide step-by-step build instructions with every field named —
   he will assemble these by hand on the device.
3. **A backfill Shortcut**, because backfill happens away from the app by definition:
   `Log time` prompts for stream, duration and day and POSTs a `source='shortcut'`,
   `confidence='reconstructed'` entry. Make it work from Siri — "log two hours to Scorpio" — and
   from the Share Sheet. Also `What's unaccounted today?`, which returns the gap total in a
   notification.
4. **An end-of-day automation** (Shortcuts *Automation* → time of day) that checks unaccounted time
   and, above a threshold, opens the Day view. Once per day, dismissible. See §8.3 — this is the
   highest-value automation in the set.
5. **Placements for those Shortcuts:** Home Screen, Lock Screen widget, Control Centre, the Action
   Button, and Back Tap. Note which placement suits which shortcut.
6. **Siri phrases** — "Hey Siri, start Scorpio" — and the exact shortcut naming that makes them work.
7. **A Shortcuts widget grid** — the closest thing to a native one-touch launcher without an App
   Store account.
8. **iPad:** the same PWA, but the realization view and the Day/backfill screens should use the
   width — multi-row backfill and gap-filling are genuinely better on a tablet. A phone layout
   stretched to 11 inches is a failure here.
9. **Optional automations,** only if they are reliable: start a Billing timer on arriving at the
   office, stop everything on entering a Sleep Focus. Propose; do not enable anything that could
   silently create false billable time. **A false billable hour is worse than a missing one.**

Do **not** propose an App Store build, TestFlight, or a paid developer account. Everything must
install from Safari and Shortcuts.

---

## 10. Build order

Each step must be independently shippable and useful the day it lands.

1. **Streams, hardcoded.** Put the six live engagements *and* the internal streams straight into
   `index.html`, ship it, start logging the same day. The data lost while building the "proper"
   version is the expensive part. *One evening, `index.html` only.*
2. **Edit, backfill and the Day view — still local-only.** No server yet. Make the record
   correctable before anything downstream depends on it, so nothing wrong gets propagated later.
   Model the supersede chain in `localStorage` exactly as it will exist in Postgres, so step 3 is a
   copy rather than a translation. *One session.*
3. **Schema and sync endpoint.** `tt` schema in `postgres_audit`, the POST endpoint behind Tailscale,
   flush-on-reconnect in the service worker. *One session.*
4. **Notion both directions.** n8n in, n8n out, including the dirty-period re-roll-up. *One session.*
5. **Fees, realization and utilization.** Load contract fees from `Договори_одит_2024`, build both
   reports. *One session — the payoff.*
6. **One-touch entry points.** Deep links, Shortcuts, widgets, Siri, the end-of-day nudge.
   *One session.*

## 11. Constraints

- **No framework, no build step, no bundler** in the PWA unless you can show the current single-file
  approach genuinely cannot carry the feature. He can read and patch this file at 23:00; keep it
  that way.
- **Offline is not a degraded mode**, it is the normal one. Every feature on the Track tab works
  with the network off.
- **Do not break the existing `tt_v1` data.** Migrate it forward — historical Billing entries have
  no stream and should land as `stream_id NULL`, `source = 'import'`, `confidence = 'timed'`, not
  be dropped.
- **No in-place edits of a synced entry, anywhere in the stack.** Corrections supersede, deletions
  void, and both carry a reason. If a code path needs `UPDATE tt.time_entry`, it is the wrong path.
- **Do not add a login, an account system, or a cloud dependency.** Tailscale is the perimeter.
- **Do not widen the scope to Audit OS or ERPNext.** That migration is a separate, much larger
  project; this schema is designed to migrate into it intact later.
- Secrets go in the existing Vaultwarden / n8n credential store. None in the repo, none in
  `index.html`.

## 12. Done means

- He can start a billable timer for a named client in one tap from a locked phone.
- Hours land in `postgres_audit` and survive a flight-mode day without loss or duplication.
- A mistimed entry can be corrected in under thirty seconds, offline, and the original is still
  there afterwards with the reason attached.
- Three days of off-grid work can be entered from memory in one sitting, and every hour of it is
  visibly marked as reconstructed.
- The Day view shows unaccounted time for today, and filling a gap takes one tap plus a stream.
- Internal development work has somewhere to go that is neither a client engagement nor untracked.
- Notion `Actual Hours` populates itself, and corrections reach it.
- `tt.realization` returns a per-engagement effective hourly rate he did not have to compute, and
  `tt.utilization` returns the billable share of his working time.
- Personal tracking (Rest, Train, Study, Pets) works exactly as it does today.
- Migration SQL, rollback notes, and the iOS shortcut recipes are written down in `docs/`.

## 13. Decisions taken

Answered by the owner, 26–27 Aug 2026. These are settled — build to them rather than re-asking.

| # | Question | Decision | What it means here |
|---|---|---|---|
| A1 | Fee currency | **EUR, all of it** | Every contract is denominated in euro, the FY2025 audits included, regardless of signature date. No BGN anywhere. No conversion, no dual display, no currency UI. |
| A2 | Fixed-fee or T&M | **All fixed-fee today; T&M expected later** | Seed every stream as `fixed`. Keep the `billing_model` column so the first T&M engagement is a config change, but do not build the variance view yet. |
| A3 | Can internal work be billable | **Sometimes — needs a per-entry billable flag** | `kind='internal'` must not force `billable=false`. Timer bar carries a billable toggle that defaults off every session and is never sticky. |
| B1 | Contractor hours | **Only his own** | No person dimension in the UI. Nullable `person` column as a hedge (see below); no picker, no cost rates. |
| B2 | Task-level or stream-level | **Stream-level is enough** | Notion write-back rolls up to the engagement. Keep `task_notion_id` nullable; build no picker for it. |
| B3 | Internal and admin streams | **All five as proposed** | Seed `DEV-AUDITOS`, `DEV-REAL`, `DEV-HOMELAB`, `EV-ADMIN`, `BD` exactly as listed in §6. |
| C1 | Working-day boundaries | **Mon–Fri 08:00–21:00 · Sat six hours · Sun none** | Gap detection per the table in §8.3. Sunday is excluded entirely — never flag a Sunday gap. |
| C2 | Reconstructed time as evidence | **Acceptable if clearly labelled** | No exclusion filter required on the export, but the timed / reconstructed split must be visible on every surface that shows hours. |
| C3 | Backfill horizon | **Unlimited, with confirmation beyond a week** | No hard block. Extra confirmation past seven days; future dates still rejected outright. |

### The one assumption still in play

**Which six hours on Saturday?** The owner specified six working hours, which is a duration; gap
detection needs a window. Assume **10:00–16:00** and put it in the config object with the other
windows, so changing it is a one-line edit rather than a question. Confirm at first use — a wrong
Saturday window manufactures phantom gaps every week and trains him to ignore the Day view, which
is the feature most likely to fix his data quality.

Sunday needs no assumption: no detection at all.

### Two cheap hedges worth taking anyway

Both cost one column and no UI. Drop either if the owner objects; do not build interface for them.

- **`person` on `tt.time_entry`**, nullable, defaulted to him. B1 says his hours only and the app
  should be built that way — but this turns "a contractor started booking time" from a migration
  into a config change.
- **`billing_model` on `tt.stream`**, defaulted to `fixed`. Same reasoning for the T&M engagements
  the owner expects to sign once this system exists.

Note that `tt.rate` already carries `target_hourly` per stream. That is what a T&M engagement will
eventually bill at, so the groundwork for A2's future is in the schema already — it just is not
wired to anything yet, and should not be.
