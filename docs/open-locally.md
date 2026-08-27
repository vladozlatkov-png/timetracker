# Open the Realization PWA locally

The GitHub Pages URL (`https://vladozlatkov-png.github.io/timetracker/`) serves **main**.
Until [PR #4](https://github.com/vladozlatkov-png/timetracker/pull/4) is merged, that URL shows the **old** app (Track / Log / Export only — no Day, Real, or streams).

The `http://127.0.0.1:8765` URL from the agent test run is **not reachable from your phone or Mac** — it only existed inside the cloud agent VM.

## Option A — Mac (two minutes)

```bash
git clone https://github.com/vladozlatkov-png/timetracker.git
cd timetracker
git checkout cursor/realization-time-tracking-38a0
python3 -m http.server 8765
```

Open in **Safari**: `http://127.0.0.1:8765`

You should see five tabs: **Track · Log · Day · Real · Export**.

Hold **Billing** (~0.6 s) → stream picker with SCORPIO-25, KUMER-25, etc.

## Option B — iPhone on the same Tailscale LAN

On the Mac (or Ubuntu VM), bind to all interfaces:

```bash
python3 -m http.server 8765 --bind 0.0.0.0
```

On the phone (Safari): `http://<tailscale-ip-of-host>:8765`

Add to Home Screen from there if you want the PWA shell.

## Option C — GitHub Pages (after merge)

1. Merge **PR #4** into `main`.
2. Wait ~1 minute for Pages to rebuild.
3. Open `https://vladozlatkov-png.github.io/timetracker/` — Realization tabs appear.

## Option D — Your homelab (persistent)

Copy the PWA files to an existing nginx root (same pattern as other services behind Tailscale / cloudflared):

```bash
sudo mkdir -p /var/www/timetracker
sudo cp index.html manifest.json sw.js icon-192.svg icon-512.svg /var/www/timetracker/
sudo cp -r icons /var/www/timetracker/
```

Serve over HTTPS on a Tailscale-only vhost. Do **not** expose the sync API on cloudflared without Cloudflare Access.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Only 3 tabs (Track, Log, Export) | You're on **main**, not the Realization branch |
| Blank page opening `index.html` from Finder | Use `http://` via a local server — `file://` breaks the service worker |
| `127.0.0.1:8765` doesn't load | That was the agent VM only — run Option A on your machine |
