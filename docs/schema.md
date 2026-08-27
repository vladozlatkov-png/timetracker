# Schema — `tt` in `postgres_audit`

System of record for hours. Notion remains the editing surface for engagements and tasks.

## Apply

```bash
# From a host that can reach postgres_audit over Tailscale:
psql "$DATABASE_URL" -f sql/001_tt_schema.sql
psql "$DATABASE_URL" -f sql/002_seed_streams.sql

# Or via the sync service:
cd server && DATABASE_URL=... npm run migrate
```

## Rollback

```bash
psql "$DATABASE_URL" -f sql/001_tt_schema_rollback.sql
```

Destroys all `tt.*` objects. Superseded/void rows are part of the audit trail — do not purge selectively.

## Design rules (non-negotiable)

| Rule | Meaning |
|---|---|
| Client UUID PK on `time_entry` | Offline POSTs retry freely: `ON CONFLICT (id) DO NOTHING` |
| Immutable rows | Never `UPDATE` a synced entry. Corrections insert a replacement with `supersedes_id`; deletions insert `void=true`. Both require `reason`. |
| Current truth | `tt.entry_current` — not the base table |
| `confidence` | `timed` / `adjusted` / `reconstructed` — visible on every report |
| `timestamptz` | Stored UTC, rendered Europe/Sofia |
| EUR only | No BGN, no FX. `fee_currency` is a hedge column, not a feature |
| Personal activities | `stream_id` nullable — Rest/Train/Study/Pets sync too |

## Fees

Seed leaves `fee_amount` NULL. Fill from `Договори_одит_2024` (Google Drive), all EUR:

```sql
UPDATE tt.stream SET fee_amount = <EUR> WHERE code = 'SCORPIO-25';
-- GLOBAL-25, KUMER-25, FASHION-25, SAMOKOV-25, B2B-25
```

## Views that are the product

- **`tt.realization`** — fixed-fee client streams: fee, hours, effective hourly, burn, reconstructed_pct. Sorted worst-deal-first in the API.
- **`tt.utilization`** — billable / internal / admin / total hours per month, utilization_pct.

T&M variance is deferred. `billing_model='tm'` streams are excluded from realization rather than mis-reported.

## Dirty roll-up

Inserting a correction or void fires `tt.mark_dirty_on_correction`, which writes `tt.notion_dirty`. The Aegis hours-out workflow recomputes from `tt.entry_current` and clears the flag — never increments.
