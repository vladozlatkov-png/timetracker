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
seven-phase roadmaps and finish phase one — so the brief below is deliberately five steps, each of
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

Keep the tracker he already uses. Add **one field** (which engagement), **one sync** (to the
Postgres he already runs), and **one report** (realization rate per engagement). Everything else in
the app stays as it is, because the rest of it works.

Three deliverables, in this order:

1. **The main schema** — Postgres, the system of record.
2. **The app** — the existing PWA extended, plus the realization view.
3. **One-touch entry points** — iPhone and iPad: Home Screen deep links, Shortcuts, widgets, Siri.

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

```sql
create schema if not exists tt;

-- Clients and engagements mirror Notion; Notion stays the editing surface, Postgres the truth for hours.
create table tt.client (
  id            uuid primary key default gen_random_uuid(),
  name          text not null,
  name_local    text,                        -- Cyrillic legal name where it differs
  notion_page_id text unique,
  active        boolean not null default true,
  created_at    timestamptz not null default now()
);

create table tt.engagement (
  id             uuid primary key default gen_random_uuid(),
  client_id      uuid not null references tt.client(id),
  name           text not null,              -- e.g. 'Statutory Audit FY2025'
  code           text unique,                -- short tap-target label, e.g. 'SCORPIO-25'
  notion_page_id text unique,
  fiscal_year    int,
  fee_amount     numeric(12,2),              -- contract fee, from Договори_одит_2024
  fee_currency   text not null default 'EUR',-- CONFIRM with the owner before defaulting
  budget_hours   numeric(8,2),               -- his own estimate, for burn
  status         text not null default 'active'
                 check (status in ('active','blocked','complete','archived')),
  started_on     date,
  due_on         date,
  sort_hint      timestamptz,                -- last touched, for ordering the picker
  created_at     timestamptz not null default now()
);

-- The append-only fact table. One row per completed timer.
create table tt.time_entry (
  id            uuid primary key,            -- generated CLIENT-side; the idempotency key
  device_id     text not null,               -- which phone/tablet/browser produced it
  activity      text not null,               -- 'billing', 'study', 'train', ...
  sub           text,                        -- sub-activity, unchanged from today
  engagement_id uuid references tt.engagement(id),   -- NULL for non-billable activities
  task_notion_id text,                       -- optional, when logged against a specific task
  billable      boolean not null default false,
  started_at    timestamptz not null,
  ended_at      timestamptz not null,
  duration_s    int generated always as
                  (extract(epoch from (ended_at - started_at))::int) stored,
  note          text,
  source        text not null default 'pwa'  -- 'pwa' | 'shortcut' | 'manual' | 'import'
                 check (source in ('pwa','shortcut','manual','import')),
  synced_at     timestamptz not null default now(),
  constraint sane_interval check (ended_at > started_at)
);

create index on tt.time_entry (engagement_id, started_at desc);
create index on tt.time_entry (activity, started_at desc);
create index on tt.time_entry (started_at desc);

-- Rates, so realization survives a fee renegotiation without rewriting history.
create table tt.rate (
  id            uuid primary key default gen_random_uuid(),
  engagement_id uuid not null references tt.engagement(id),
  target_hourly numeric(10,2) not null,       -- what an hour SHOULD earn
  currency      text not null default 'EUR',
  valid_from    date not null,
  valid_to      date
);
```

Plus a view that is the actual product:

```sql
create view tt.realization as
select e.id, e.code, c.name as client, e.fee_amount, e.fee_currency,
       round(sum(t.duration_s)/3600.0, 2)                      as hours,
       e.budget_hours,
       round(sum(t.duration_s)/3600.0 / nullif(e.budget_hours,0) * 100, 1) as burn_pct,
       round(e.fee_amount / nullif(sum(t.duration_s)/3600.0, 0), 2)        as effective_hourly
from tt.engagement e
join tt.client c on c.id = e.client_id
left join tt.time_entry t on t.engagement_id = e.id
group by e.id, c.name;
```

**Properties the schema must have, however you shape it:**

- **Client-generated UUID primary key on `time_entry`.** The phone is offline-first; the same entry
  will be POSTed more than once. `on conflict (id) do nothing` must make retries free.
- **Append-only.** Never mutate or delete a synced entry from a sync path. Corrections are new rows
  or an explicit edit path with an audit trail — this is an auditor's own time record and may end up
  as evidence in a client file.
- **`timestamptz` everywhere**, stored UTC. He is in Europe/Sofia, which observes DST; a
  local-naive timestamp will silently corrupt an hour twice a year.
- **Non-billable activities keep working.** `engagement_id` is nullable. Rest, Train, Study and
  Pets must sync too — they are the control group, and the Study Cockpit (the next project) will
  reuse this exact table with a subject dimension instead of an engagement.
- **Currency is a column, not an assumption.** Ask the owner whether fees are in BGN or EUR before
  defaulting, and be prepared for both to appear.
- Provide **forward migration SQL** and a documented rollback. Do not use an ORM's auto-migrate.

## 7. Deliverable 2 — the app

### 7.1 Engagement picker

Tapping `Billing` must offer live engagements — most recently used first — instead of the current
generic sub list. Ordering comes from `sort_hint`; cache the list in `localStorage` so it is
available with no network. All other activities keep their existing sub-activity behaviour
untouched.

Keep the interaction he already has: **one tap starts the last-used engagement immediately**, hold
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
GET  /api/engagements    → [ { id, code, client, sort_hint } ]
GET  /api/realization    → rows from tt.realization
```

Auth: a static bearer token in the device's local storage is acceptable **only** because the
endpoint is Tailscale-only. If it is ever exposed through cloudflared, put Cloudflare Access in
front of it. Do not build a login screen.

### 7.3 Notion write-back

An n8n workflow, both directions:

- **In:** engagements from Notion → `tt.engagement` (upsert on `notion_page_id`).
- **Out:** hours per engagement/task → Notion `Actual Hours` on the task rows that already have the
  field. Roll up on a schedule, not per entry; make it idempotent, since it will re-run.

Copy the credential and node patterns from the existing Marty_Party workflow in `workflows/`.

### 7.4 The realization view

The screen he opens weekly. Per engagement: fee, hours to date, **effective hourly rate**, burn
against his own `budget_hours`, and a clear flag when an engagement crosses the point where it
stops being worth doing at that fee. Sort by effective hourly ascending — the worst deal first, on
purpose.

Build it as a fourth tab in the PWA if it can be done in plain JS in keeping with the existing
file, or as a Metabase dashboard if that is materially faster. State which you chose and why.

### 7.5 Timesheet export

Per-engagement, per-period, in a form an audit file will accept — not a raw dump of eight activity
types. Keep the existing day/week/month CSV export working unchanged alongside it.

## 8. Deliverable 3 — one-touch on iPhone and iPad

The goal is **starting the right timer in one physical action**, from a cold phone. Deliver all of
the following that survive contact with current iOS, and say plainly which ones did not:

1. **Deep-linked Home Screen icons.** Support `?start=<engagement-code>` in the PWA so a URL starts
   that engagement's timer on load and shows a confirmation, not a menu. Then one Safari
   "Add to Home Screen" bookmark per engagement gives a literal one-touch grid. Give each a
   distinguishable icon — generate per-engagement SVG icons from the existing `icon-512.svg`.
2. **Shortcuts that hit the API directly**, so they work without opening the app: `Start <engagement>`,
   `Stop timer`, `What am I tracking?`, `Hours on <engagement> this month`. Use *Get Contents of URL*
   against the Tailscale endpoint. Provide step-by-step build instructions with every field named —
   he will assemble these by hand on the device.
3. **Placements for those Shortcuts:** Home Screen, Lock Screen widget, Control Centre, the Action
   Button, and Back Tap. Note which placement suits which shortcut.
4. **Siri phrases** — "Hey Siri, start Scorpio" — and the exact shortcut naming that makes them work.
5. **A Shortcuts widget grid** — the closest thing to a native one-touch launcher without an App
   Store account.
6. **iPad:** the same PWA, but the realization view should use the width. A phone layout stretched
   to 11 inches is a failure here.
7. **Optional automations,** only if they are reliable: start a Billing timer on arriving at the
   office, stop everything on entering a Sleep Focus. Propose; do not enable anything that could
   silently create false billable time. **A false billable hour is worse than a missing one.**

Do **not** propose an App Store build, TestFlight, or a paid developer account. Everything must
install from Safari and Shortcuts.

---

## 9. Build order

Each step must be independently shippable and useful the day it lands.

1. **Engagement field, hardcoded.** Put the six live engagements straight into `index.html`, ship it,
   start logging the same day. The data lost while building the "proper" version is the expensive
   part. *One evening, `index.html` only.*
2. **Schema and sync endpoint.** `tt` schema in `postgres_audit`, the POST endpoint behind Tailscale,
   flush-on-reconnect in the service worker. *One session.*
3. **Notion both directions.** n8n in, n8n out. *One session.*
4. **Fees and the realization view.** Load contract fees from `Договори_одит_2024`, build the report.
   *One session — the payoff.*
5. **One-touch entry points.** Deep links, Shortcuts, widgets, Siri. *One session.*

## 10. Constraints

- **No framework, no build step, no bundler** in the PWA unless you can show the current single-file
  approach genuinely cannot carry the feature. He can read and patch this file at 23:00; keep it
  that way.
- **Offline is not a degraded mode**, it is the normal one. Every feature on the Track tab works
  with the network off.
- **Do not break the existing `tt_v1` data.** Migrate it forward — historical Billing entries have
  no engagement and should land as `engagement_id NULL` with a `source` of `import`, not be dropped.
- **Do not add a login, an account system, or a cloud dependency.** Tailscale is the perimeter.
- **Do not widen the scope to Audit OS or ERPNext.** That migration is a separate, much larger
  project; this schema is designed to migrate into it intact later.
- Secrets go in the existing Vaultwarden / n8n credential store. None in the repo, none in
  `index.html`.

## 11. Done means

- He can start a billable timer for a named client in one tap from a locked phone.
- Hours land in `postgres_audit` and survive a flight-mode day without loss or duplication.
- Notion `Actual Hours` populates itself.
- `tt.realization` returns a per-engagement effective hourly rate he did not have to compute.
- Non-billable tracking works exactly as it does today.
- Migration SQL, rollback notes, and the iOS shortcut recipes are written down in `docs/`.

## 12. Open questions to put to the owner before building

Ask these rather than guessing — each one changes the schema or the maths:

1. Fee currency — BGN or EUR — and whether historical contracts mix the two.
2. Are engagement fees fixed-fee only, or are some time-and-materials?
3. Should contractor hours be tracked here too, or only his own?
4. Should `EV` (his own company work) be an engagement like any other, so its cost is visible, or
   stay a separate non-billable bucket?
5. Does an entry ever need to attach to a specific Notion task, or is engagement-level enough for now?
