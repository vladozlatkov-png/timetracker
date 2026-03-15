# Time Tracker PWA — Installation Guide

## What's in this folder

| File | Purpose |
|------|---------|
| `index.html` | The entire app (all-in-one) |
| `manifest.json` | PWA metadata (name, icon, colors) |
| `sw.js` | Service worker — enables offline use |
| `icon-192.svg` | App icon (home screen) |
| `icon-512.svg` | App icon (splash screen) |

---

## Option A — Host on GitHub Pages (free, 5 minutes)

1. Create a free account at github.com
2. Create a new repository, name it `timetracker`, set it to **Public**
3. Upload all 5 files
4. Go to Settings → Pages → Source: **main branch / root**
5. Your app is live at `https://yourusername.github.io/timetracker`
6. Open that URL on your phone → "Add to Home Screen"

---

## Option B — Host on Netlify (free, 3 minutes, drag & drop)

1. Go to netlify.com, create a free account
2. Drag and drop this entire folder onto the Netlify dashboard
3. You get a URL like `https://random-name.netlify.app`
4. Open on phone → Add to Home Screen

---

## Option C — Self-host on a VPS (Nginx)

```bash
# Install Nginx
sudo apt update && sudo apt install nginx -y

# Copy files
sudo mkdir -p /var/www/timetracker
sudo cp index.html manifest.json sw.js icon-192.svg icon-512.svg /var/www/timetracker/

# Create Nginx config
sudo nano /etc/nginx/sites-available/timetracker
```

Paste this config:
```nginx
server {
    listen 80;
    server_name your-server-ip;
    root /var/www/timetracker;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/timetracker /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

For HTTPS (required for PWA install prompt on Android):
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com
```

---

## Install on iPhone

1. Open the URL in **Safari** (must be Safari, not Chrome)
2. Tap the **Share** button (box with arrow)
3. Tap **Add to Home Screen**
4. Tap **Add** — done!

## Install on Android

1. Open the URL in **Chrome**
2. Tap the **three-dot menu**
3. Tap **Add to Home Screen** (or an install banner may appear automatically)
4. Tap **Install** — done!

---

## How the app works

- **Single tap** an activity → starts timer immediately
- **Hold 0.6 seconds** → opens sub-activity picker
- All data is saved in your phone's localStorage (stays on device)
- Works fully offline after first load
- **Log tab** → browse all past entries
- **Export tab** → download daily / weekly / monthly CSV files

---

## Data & Privacy

All data is stored locally on your device using `localStorage`.
Nothing is sent to any server. To back up your data, use the CSV export regularly.
