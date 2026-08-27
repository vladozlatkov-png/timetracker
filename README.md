# Time Tracker PWA — Realization

Engagement-aware time tracking for Easy Ventures. Single-file PWA (no build step),
Postgres `tt` schema as system of record, Tailscale sync API, Aegis n8n Notion roll-up.

## What's in this folder

| Path | Purpose |
|------|---------|
| `index.html` | The entire PWA — Track, Log, Day, Real, Export |
| `manifest.json` / `sw.js` | PWA metadata + offline cache |
| `icon-*.svg` / `icons/` | App icon + per-stream Home Screen glyphs |
| `sql/` | Forward migration, rollback, seed streams |
| `server/` | Sync API (`POST /api/entries`, realization, day gaps) |
| `workflows/` | Aegis Notion in + hours out (not Marty Party) |
| `docs/` | Schema, sync, migration, iOS Shortcuts recipes |

## Day-one use (no server yet)

1. Open `index.html` (or host the folder).
2. Tap **Billing** → starts last-used stream; hold → stream picker (clients above the divider, internal/admin below).
3. Log / Day / Real tabs work fully offline.
4. Existing `tt_v1` data migrates to `tt_v2` automatically.

## Full stack

See:

- [`docs/schema.md`](docs/schema.md) — apply `sql/001` + `sql/002`, fill fees from `Договори_одит_2024` (EUR)
- [`docs/sync-api.md`](docs/sync-api.md) — deploy `server/`, paste Tailscale URL + bearer token in Export
- [`docs/migration.md`](docs/migration.md) — localStorage + Notion credential wiring
- [`docs/ios-shortcuts.md`](docs/ios-shortcuts.md) — deep links, Shortcuts, Siri, EOD nudge

## Interaction model (unchanged)

- **Single tap** an activity → starts timer immediately  
  (Billing → last-used stream)
- **Hold 0.6 s** → sub-activity or stream picker
- Corrections supersede; deletions void; both need a reason
- Reconstructed / adjusted hours are labelled everywhere

## Realization view choice

Built as the **Real** tab in the PWA (plain JS, same file). Weekly effective-hourly
and utilization belong on the phone he already opens — Metabase can still point at
`tt.realization` / `tt.utilization` for larger screens later.

## Bot lane

This project is **Aegis**. Marty Party must not touch it.
