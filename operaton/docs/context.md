# Fast-forward context

Read this first in a new session. It is the standing picture; dated session
logs live in [`sessions/`](sessions/).

> **There is no chat-history search tool in this environment.** A new session
> cannot recover prior conversations. Everything below was reconstructed from
> the Notion workspace and this repo — that reconstruction is the point of this
> file, so you don't have to repeat it. Notion search *does* work and is the
> best source of ground truth; the page IDs are at the bottom.

Last updated: 2026-07-31.

## Who and what

Vlado Zlatkov — registered auditor, Bulgaria. Statutory audits under
НСС/BGAAP, FY2025 season. Two billing entities: **AFBC** (commercial biller,
audit engagements) and **Easy Ventures / EV** (non-audit clients). Engagement
document refs use the `EV-YYYY-CODE` pattern regardless of biller.

"Audit OS" is the in-house engagement operating system.

## The estate

| Plane | System | Where |
|---|---|---|
| System of record | Postgres `workflow.*` | Audit OS database |
| Control/CRM surface | Notion (Engagements, Clients, Tasks DBs) | read-only mirror of `workflow.*` |
| Engagement + books platform | ERPNext 15.108.3 + `erpnext_bulgaria` | frappe-lxc CT100, Proxmox `pve-lenovo`, 192.168.68.77, site `frappe.localhost` |
| Skills / execution | 13 Claude skills, Waves 1–3 complete 2026-06-10 | Mac Studio skills stack |
| Automation | n8n | — |
| Evidence | Synology NAS | `/Audit_Engagements/...` |

## What is frozen vs live

**Frozen (do not work from):** the *Audit OS Design Task List* — the original
Notion + n8n + Synology three-plane design. Banner added 2026-07-03 marking it
superseded. It still contains useful historical detail (folder structure,
naming convention, interface freeze list) but its phase checklists are dead.

**Superseded by:** Audit Pipeline Spec v1 (2026-05-27), the skills build, and
the ERPNext Gap Analysis (2026-06-01, in Google Drive — not yet read in any
session).

**Live:** "Audit OS backbone (slice 2)", writing to Notion as recently as
2026-07-31 08:35. Postgres `workflow.*` is authoritative; Notion engagement
cards carry the banner *"mirrored one-way from Postgres `workflow.*` — do not
edit them here; they will be overwritten."*

## The existing state model

This already works in production. It is a hand-rolled workflow engine.

- **Status enum:** draft / planning / fieldwork / completion / reporting /
  closed / blocked
- **Gate codes:** `G-SANCTIONS`, `G-INDEPENDENCE`, `G-WP-CONCLUDED`, `G-GC`,
  `G-EQCR`, `G-EVIDENCE-LOCK`
- **Step keys:** phase-prefixed — `acc-memo`, `pln-tb2ls`, `fw-pbc-chase`,
  `fw-wp:{revenue,receivables,ppe,related_parties,expenses}`, `fw-je`,
  `fw-rp`, `fw-est`
- **Registry:** 31 steps, content-hashed. Card field reads
  `24/31 · registry f19302d · derived 2026-07-31 11:20`
- **Blocked Reason:** computed, format
  `G-X open, G-Y open · next: step-a, step-b`
- **Card flags:** Materiality Defined, Risk Assessment Complete, Partner
  Sign-off, Completion Checklist Signed, Escalation Required, Folder Created

## Live engagements (2026-07-31)

| Engagement | Code | Status | Progress | Note |
|---|---|---|---|---|
| КУМЕР ООД | KUM | fieldwork | 24/31 | `G-WP-CONCLUDED`, `G-EVIDENCE-LOCK` open |
| Global Exchange ООД | GLX | fieldwork | 11/31 | fee EUR 1,800, delivery 30.09.2026 |
| Енлайтмент ООД | — | — | — | on backbone slice 2 |
| Kinstellar Sofia | — | — | — | БУЛСТАТ 176798908 |

July batch, created 2026-07-23, **not yet started** — these are the pilot
candidates: CIC (КОМПАНИЯ ЗА МЕЖДУНАРОДНИ КОНГРЕСИ, EUR 2,500),
ДИВЕРТИМЕНТО, МОСТ ЕНЕРДЖИ АД (EUR 4,000), Most Energy Gas, БИ ТУ БИ (B2B),
plus МСЕ Проект-1 (an AUP engagement, ISRS 4400 — not a statutory audit).

## This repo

`vladozlatkov-png/timetracker` is a standalone time-tracker PWA plus a
Marty_Party n8n Telegram workflow. It has **nothing to do with Audit OS** —
Audit OS lives on the Mac Studio and frappe-lxc, neither reachable from a
session container. GitHub access is scoped to this repo only.

The `operaton/` subdirectory was scaffolded here because the user chose this
repo when asked. If Audit OS ever gets its own repo, `operaton/` should move.

Mild irony worth remembering: the old roadmap explicitly postpones time
tracking to Phase 7, "postpone intentionally".

## The Operaton decision

New as of 2026-07-31 — nothing in Notion mentions Operaton, Camunda, or BPMN,
so there is no earlier thread to find.

**Framing that matters:** the question is not "should there be an orchestrator"
— one exists and works. It is "should the hand-rolled one be replaced by a BPMN
engine". The four gaps that justify it: human task inbox, timers/escalation, a
visual model, and an incident queue. The honest competitive alternative is a
read UI over `workflow.*`, which is far cheaper and closes only the third gap.

**Decision taken:** Operaton owns process control (phases, human tasks, timers,
incidents). `workflow.*` keeps audit content. Joined by a new `orchestrator`
schema that touches nothing existing. Full reasoning in
[`architecture.md`](architecture.md).

**The rule:** the 31-step programme is data, not diagram. Adding a step must
stay an `INSERT`, never a redeploy plus instance migration.

**Pilot constraint:** one *not-yet-started* engagement (CIC or ДИВЕРТИМЕНТО).
Never КУМЕР or GLX — both mid-fieldwork against a 30.09.2026 deadline.

## Grounded Operaton facts

- Operaton 2.0 released 2026-03-20; Spring Boot 4 / Spring Framework 7
- Apache 2.0; community fork of Camunda 7 CE after its EOL in October 2025
- REST API, DB schema, and deployable models are Camunda 7 compatible
- Image `operaton/operaton:latest` on Docker Hub, port 8080, `demo`/`demo`
- REST base path `/engine-rest`; **unauthenticated by default**
- DB env vars: `DB_DRIVER`, `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`, `WAIT_FOR`
- Current extension namespace `http://operaton.org/schema/1.0/bpmn`
  (`operaton:`). The legacy `http://camunda.org/schema/1.0/bpmn` is retained
  for backwards compatibility, so Camunda Modeler round-trips still deploy.

## Open questions

1. **Repo home.** Does Audit OS get its own repository? `operaton/` sitting in
   `timetracker` is an accident of access scope.
2. **`orchestrator.v_steps` needs repointing** at the real `workflow.*`
   registry. The seeded stub is placeholder data. Nobody has seen the real
   registry's table shape — it isn't reachable from a session container.
3. **`historyTimeToLive` is set to `P10Y`** as a guess. Confirm against the
   firm's retention policy.
4. **Four integration endpoints unconfigured**: `SANCTIONS_API_URL`,
   `AUDIT_STEP_DISPATCH_URL`, `PBC_CHASE_WEBHOOK`, `ISSUE_REPORT_WEBHOOK`.
   Handlers raise incidents until they're set — by design.
5. **ERPNext overlap.** ERPNext is the engagement + books platform. How its
   engagement records relate to Operaton process instances has not been
   thought through at all.
6. **Nothing has run against a live engine.** See Verification in the README.

## Environment gotchas

- **No conversation-history tool.** Don't promise to search past chats.
- **`docker pull` is blocked** — 403 from `production.cloudfront.docker.com`
  under the egress policy. Don't retry or route around it. Local Postgres 16
  *is* available at `/usr/lib/postgresql/16/bin` and works for schema testing
  (initdb under `/var/tmp`, not the scratchpad — socket permissions).
- **Notion MCP works** and is the best ground truth.
- **GitHub is scoped to `vladozlatkov-png/timetracker`.** No `gh` CLI; use the
  `mcp__github__*` tools.
- Session containers are ephemeral — commit and push anything worth keeping.

## Notion page IDs

| Page | ID |
|---|---|
| Audit OS Design Task List (frozen) | `336d77e4-d8d8-80ad-9215-d376f750ebb5` |
| Audit OS v1.0 (parent) | `d6e41f2d-e9f8-4fc9-bd2b-37e768394039` |
| Engagements DB | `1971d250-6e7a-4c8c-a797-f2770fe9137c` |
| Engagements data source | `collection://9a26c585-88e5-434d-86e1-7804e1fe2121` |
| КУМЕР ООД | `393d77e4-d8d8-8182-b445-f77ae1787c3e` |
| Global Exchange ООД | `393d77e4-d8d8-81f5-a20d-eae7ccb45c81` |
| ERPNext live instance — facts & go-live | `392d77e4-d8d8-813c-bad5-e6fd2e9c4ce0` |
| Audit OS — Materiality Procedure | `35dd77e4-d8d8-812f-9866-c252717e2ad4` |
| CLAUDE.md & Skills — Backlog & References | `35cd77e4-d8d8-819c-93ee-fed5fcab6552` |
