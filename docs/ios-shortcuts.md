# iOS one-touch — Shortcuts, widgets, Siri, Home Screen

Everything installs from Safari + Shortcuts. No App Store, no TestFlight, no paid developer account.

Replace `https://TT_HOST` with the Tailscale hostname or IP of the sync API (e.g. `http://100.x.x.x:8787`).
Replace `TOKEN` with the bearer token from Vaultwarden.
Replace `https://PWA_HOST` with wherever the PWA is served.

---

## 1. Deep-linked Home Screen icons

Each engagement gets a URL that starts its timer on load:

```
https://PWA_HOST/index.html?start=SCORPIO-25
https://PWA_HOST/index.html?start=GLOBAL-25
https://PWA_HOST/index.html?start=KUMER-25
https://PWA_HOST/index.html?start=FASHION-25
https://PWA_HOST/index.html?start=SAMOKOV-25
https://PWA_HOST/index.html?start=B2B-25
https://PWA_HOST/index.html?start=DEV-REAL
https://PWA_HOST/index.html?start=EV-ADMIN
```

Day view (for the end-of-day automation):

```
https://PWA_HOST/index.html?view=day
```

**Add to Home Screen (per engagement):**

1. Open the URL in **Safari**.
2. Confirm the banner shows `Started SCORPIO-25` (etc.).
3. Share → **Add to Home Screen**.
4. Name it `Scorpio` / `Kumer` / …
5. For a distinguishable icon: before adding, open the matching file from `icons/icon-SCORPIO-25.svg` (long-press → Add to Photos, or host it and use as apple-touch-icon). Safari uses the page's apple-touch-icon by default; for per-engagement icons the practical path is:
   - Host `icons/icon-SCORPIO-25.svg` at a path, or
   - Use Shortcuts tiles (below) which render their own glyphs.

**What works today on iOS:** custom bookmark titles + the shared PWA icon. True per-bookmark custom icons without a Shortcut are unreliable on current iOS — Safari reuses the site's apple-touch-icon. **Use the Shortcuts widget grid (§7) when you need a colour-coded one-touch launcher.** Per-engagement SVGs in `icons/` are ready for when you host them as separate mini start pages if desired.

---

## 2. Shortcuts that hit the API directly

Open **Shortcuts** → **+** → build each below. All use **Get Contents of URL**.

### Start \<stream\> (opens PWA deep link — timer lives on device)

Name: `Start Scorpio`

1. **Open URLs** → `https://PWA_HOST/index.html?start=SCORPIO-25`

Duplicate per stream. This is the reliable "start timer" path because the running timer is client-side / offline-first. A server-only start would create a row without a live stop control on the phone.

### Stop timer

Name: `Stop timer`

1. **Open URLs** → `https://PWA_HOST/index.html`  
   Then in the PWA tap Stop — or use the PWA itself from the Home Screen.

True headless stop without opening the app is **not delivered**: the active timer state lives in the device's `localStorage`, not on the server. Shipping a server-side "open timer" would invent billable intervals the phone never confirmed. **A false billable hour is worse than a missing one.**

### What am I tracking?

Name: `What am I tracking`

1. **Get Contents of URL**
   - URL: `https://TT_HOST/api/status`
   - Method: GET
   - Headers: `Authorization` = `Bearer TOKEN`
2. **Get Dictionary Value** → `last_entry`
3. **Show Notification** with `stream code` + `started_at` (or "Nothing recent on server — check the PWA timer bar")

### Hours on \<stream\> this month

Name: `Hours Scorpio this month`

1. **Get Contents of URL**
   - URL: `https://TT_HOST/api/hours/SCORPIO-25`
   - Method: GET
   - Headers: `Authorization` = `Bearer TOKEN`
2. **Show Result** / Notification: `Hours this month: {hours_month}`

---

## 3. Backfill Shortcut — "Log time"

Name: `Log time`  
(Siri: "Hey Siri, Log time" / add Ask for Input phrases below)

1. **List** → SCORPIO-25, GLOBAL-25, KUMER-25, FASHION-25, SAMOKOV-25, B2B-25, DEV-AUDITOS, DEV-REAL, DEV-HOMELAB, EV-ADMIN, BD
2. **Choose from List** → store as `Stream`
3. **Ask for Input** (Number / Text) → "How long? (e.g. 2h or 45m)" → `Duration`
4. **Ask for Input** → "Which day? (YYYY-MM-DD, blank = today)" → `Day`
5. **If** Day is empty → Set Day to Today's date (Format Date → `yyyy-MM-dd`)
6. Parse duration in a **Run JavaScript for Automation** or pre-compute: simplest path — Ask for Input as minutes (Number), convert:
   - **Calculate** `Duration * 60` → seconds
7. Build start/end:
   - Start = Day at 09:00 local
   - End = Start + duration
8. **Get Contents of URL**
   - URL: `https://TT_HOST/api/backfill`
   - Method: POST
   - Headers: `Authorization` = `Bearer TOKEN`, `Content-Type` = `application/json`
   - Body (JSON):

```json
{
  "device_id": "shortcut-iphone",
  "activity": "billing",
  "stream_code": "SCORPIO-25",
  "billable": false,
  "started_at": "2026-08-27T06:00:00.000Z",
  "ended_at": "2026-08-27T08:00:00.000Z",
  "note": "from Shortcut",
  "source": "shortcut",
  "confidence": "reconstructed",
  "reason": "shortcut backfill"
}
```

Use Shortcut variables for `stream_code`, timestamps, note. **Leave `billable: false` by default.** Add a separate confirmation Ask ("Billable? yes/no") if you need a billable backfill — never default it on.

**Share Sheet:** In Shortcut Details → enable **Show in Share Sheet** → accept Text input as the note.

**Siri:** Details → **Add to Siri** → phrase `log two hours to Scorpio` works best when the Shortcut is named `Log Scorpio` and hard-codes the stream, with Ask only for duration.

### What's unaccounted today?

Name: `What's unaccounted today`

1. **Format Date** Current Date → `yyyy-MM-dd` → `Day`
2. **Get Contents of URL** → `https://TT_HOST/api/day/{Day}`
3. **Get Dictionary Value** → `unaccounted_h`
4. **Show Notification** → `Unaccounted today: {unaccounted_h}h`

---

## 4. End-of-day automation

1. Shortcuts → **Automation** → **Time of Day** → 19:00 → Daily → Run Immediately (or After Confirmation).
2. Actions:
   1. Run `What's unaccounted today?`
   2. **If** `unaccounted_h` `is greater than` `1`
   3. **Open URLs** → `https://PWA_HOST/index.html?view=day`
3. Once per day, dismissible. Do not loop. Do not auto-fill.

The PWA also nudges once per local day after 19:00 if unaccounted > 1h (`EOD_UNACCOUNTED_THRESHOLD_H` in `index.html`).

---

## 5. Placements

| Placement | Best shortcuts |
|---|---|
| Home Screen | `Start Scorpio` … one icon per live engagement; `Log time` |
| Lock Screen widget | `What's unaccounted today?` (single tap → notification) |
| Control Centre | `Stop timer` / `Start Scorpio` (Controls picker → Shortcut) |
| Action Button (iPhone 15 Pro+) | `Start Scorpio` or `Log time` — highest-frequency action |
| Back Tap | `What's unaccounted today?` (Settings → Accessibility → Touch → Back Tap) |

---

## 6. Siri phrases

Name the Shortcut exactly as the phrase you want after "Hey Siri, …":

| Shortcut name | Say |
|---|---|
| `Start Scorpio` | "Hey Siri, Start Scorpio" |
| `Start Kumer` | "Hey Siri, Start Kumer" |
| `Log time` | "Hey Siri, Log time" |
| `What's unaccounted today` | "Hey Siri, What's unaccounted today" |

Bulgarian phrases work if you name the Shortcut in Bulgarian (`Старт Скорпио`).

---

## 7. Shortcuts widget grid

Closest thing to a native one-touch launcher:

1. Build one Shortcut per stream (`Start Scorpio`, …).
2. Long-press Home Screen → **+** → **Shortcuts** → **Grid** (large or medium).
3. Edit widget → pick the folder that holds the Start-* shortcuts.
4. Optional: set each Shortcut's icon colour (Shortcut Details → Icon) to match `icons/` accents — client purple, internal blue, admin amber.

---

## 8. iPad

Same PWA URL. From ~900px width:

- Day, Real, and Export use a two-column layout.
- Multi-day backfill form goes wide (`Multi-day` on the Log tab).

Add the PWA to the iPad Home Screen separately (Safari → Share → Add to Home Screen). Landscape is supported (`orientation: any` in the manifest).

---

## 9. Optional automations — propose only

| Idea | Verdict |
|---|---|
| Start Billing on arriving at the office (Personal Automation → Arrive) | **Do not enable unattended.** Arrival ≠ billable work. If used, open the stream picker — never auto-start billable. |
| Stop everything on Sleep Focus | Safe if it only opens the PWA or shows a notification "Timer still running?". Do not POST a stop/billable row from Focus alone without confirmation. |

**A false billable hour is worse than a missing one.**

---

## What did not survive contact with current iOS

| Wanted | Reality |
|---|---|
| Per-engagement Home Screen icons with unique glyphs from Safari bookmarks alone | Unreliable — Safari reuses the site apple-touch-icon. Use Shortcuts widget icons or host mini start pages. |
| Headless Stop timer via API without opening the app | Not shipped — timer state is device-local by design. |
| Silent Arrive → start billable | Explicitly rejected. |
