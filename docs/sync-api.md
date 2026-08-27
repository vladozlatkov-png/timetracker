# Sync API

Small Node service in `server/`. Tailscale-only perimeter. If ever exposed via cloudflared, put Cloudflare Access in front — do not build a login screen.

## Deploy

```bash
cd server
cp .env.example .env   # fill DATABASE_URL + TT_BEARER_TOKEN from Vaultwarden
npm install
npm run migrate        # applies sql/001 + sql/002
npm start              # :8787
```

Docker:

```bash
docker build -t tt-sync ./server
docker run -d --name tt-sync --network=… \
  -e DATABASE_URL=postgres://… \
  -e TT_BEARER_TOKEN=… \
  -p 8787:8787 tt-sync
```

Point the PWA at the Tailscale IP/hostname under **Export → Sync endpoint**. Token stays in the device's `localStorage` only.

## Endpoints

All `/api/*` require `Authorization: Bearer <TT_BEARER_TOKEN>`.

| Method | Path | Body / notes |
|---|---|---|
| POST | `/api/entries` | `{ device_id, entries: […] }` → `{ accepted: [ids] }`. One write path for live, corrections, voids, backfills. |
| POST | `/api/backfill` | Shortcut helper; stamps `source=shortcut`, `confidence=reconstructed`. |
| GET | `/api/streams` | Active streams for the picker |
| GET | `/api/realization` | Rows from `tt.realization`, worst effective hourly first |
| GET | `/api/utilization` | Rows from `tt.utilization` |
| GET | `/api/day/:YYYY-MM-DD` | Current entries + gaps for that local day |
| GET | `/api/hours/:code` | Hours on stream this month (Shortcuts) |
| GET | `/api/status` | Last entry summary |
| GET | `/health` | No auth |

## Entry shape (POST)

```json
{
  "id": "client-generated-uuid",
  "activity": "billing",
  "sub": "SCORPIO-25",
  "stream_id": null,
  "stream_code": "SCORPIO-25",
  "billable": true,
  "started_at": "2026-08-27T07:00:00.000Z",
  "ended_at": "2026-08-27T09:30:00.000Z",
  "note": null,
  "source": "pwa",
  "confidence": "timed",
  "supersedes_id": null,
  "void": false,
  "reason": null
}
```

`stream_code` is accepted because the PWA ships with local seed ids that are not Postgres UUIDs. The server resolves code → `tt.stream.id`.

## Offline behaviour

- Timer start/stop never awaits the network.
- Entries land in `localStorage` (`tt_v2`) and a sync queue (`tt_sync_queue`).
- Flush on online event, every 30s, and on manual "Flush queue now".
- Nothing is removed from the queue until the server acknowledges the id.
- Retries are free: `ON CONFLICT (id) DO NOTHING`.
