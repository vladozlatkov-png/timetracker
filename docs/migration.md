# Migration notes

## localStorage `tt_v1` → `tt_v2`

On first load the PWA:

1. Reads `tt_v1` if `tt_v2` is empty.
2. Rewrites each entry with a new client UUID, `source='import'`, `confidence='timed'`, `stream_id=null`.
3. Writes `tt_v2`. Does **not** delete `tt_v1` (safe rollback: clear `tt_v2` to re-migrate, or keep both).

Historical Billing rows have no stream — they stay `stream_id NULL`. That is intentional; do not invent a client after the fact.

`EV` as a Billing sub-activity is retired. New Easy Ventures admin time goes to stream `EV-ADMIN`. Old rows keep `sub='EV'` as text.

## Postgres

```bash
psql "$DATABASE_URL" -f sql/001_tt_schema.sql
psql "$DATABASE_URL" -f sql/002_seed_streams.sql
```

Rollback:

```bash
psql "$DATABASE_URL" -f sql/001_tt_schema_rollback.sql
```

## Fees

Not auto-loaded — `Договори_одит_2024` was not available to the build agent. After deploy:

```sql
UPDATE tt.stream SET fee_amount = <EUR> WHERE code = 'SCORPIO-25';
-- repeat for GLOBAL-25 KUMER-25 FASHION-25 SAMOKOV-25 B2B-25
```

Also paste the same numbers into the PWA: DevTools → `localStorage.tt_streams` → edit `fee_amount`, or wait for Notion-in sync once fees live on engagement pages.

## n8n

Import:

- `workflows/Aegis_Realization_Notion_In.json`
- `workflows/Aegis_Realization_Hours_Out.json`

Wire credentials to **Aegis** Notion + AuditOS Postgres (same Postgres credential id pattern as Marty_Party: `postgres-audit-os`). Do **not** attach Marty Party Telegram credentials. Adjust Notion property names if the live Engagements/Tasks schema differs from the assumed labels.
