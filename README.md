# Smart Calendar display

An animated calendar for a TV, driven by a Raspberry Pi Zero 2 W. It rotates through three screens:

| Screen | Shows | Time on screen |
|---|---|---|
| **Month** | 4 weeks starting this Sunday, with event pills | 15 s |
| **This week** | Sunday to Saturday timeline (7am to 9pm), all-day bars, a red "now" line | 18 s |
| **Today** | Monthly flyer, today's timeline, weather, fun fact, quote | 22 s |

GitHub pulls Planning Center data 3 times a day and publishes the site for free on GitHub Pages. The Pi only opens the web page.

```
Planning Center ─┐
Open-Meteo ──────┼─► GitHub Action (3×/day) ─► data.json ─► GitHub Pages ─► Pi (Chromium kiosk) ─► TV
facts/quotes ────┘
```

## Files

```
site/index.html            the whole display (HTML/CSS/JS, no build step)
site/data.json             sample data; replaced on every Action run
site/assets/bg-*.jpg       sky backgrounds from your mockup
site/assets/flyer.png      default flyer for the Today screen
scripts/build_data.py      fetches Planning Center + weather, writes data.json
content/facts.txt          fun facts, one per line (rotates daily)
content/quotes.txt         quotes: text | author
.github/workflows/update.yml   the 3×/day schedule + deploy
pi/setup-kiosk.sh          one-time Pi setup
```

## 1. Planning Center token

1. Go to **api.planningcenteronline.com/personal_access_tokens** and create a token.
2. Copy the **Application ID** and **Secret**.
3. The token acts as your account. A login with view-only Calendar access is safest.

## 2. GitHub repo

1. Create a new repository and upload everything in this folder (keep the `.github` folder).
2. **Settings → Secrets and variables → Actions**
   - *Secrets* tab: add `PCO_APP_ID` and `PCO_SECRET`.
   - *Variables* tab (optional):
     - `LATITUDE`, `LONGITUDE`: for the weather card, e.g. `33.4484` and `-112.0740`.
     - `TIMEZONE`: defaults to `America/Denver`.
     - `PCO_ONLY_PUBLIC`: `true` to show only events visible in Church Center.
     - `PCO_APPROVED_ONLY`: defaults to `true` (hides pending or rejected events).
3. **Settings → Pages → Source:** select **GitHub Actions**.
4. **Actions → Update calendar → Run workflow** to run it the first time. Your site will be at `https://<user>.github.io/<repo>/`.

Updates run at about 5am, 11am and 5pm Mountain time, and also on every push. To change the schedule, edit the `cron` lines in `update.yml` (they're in UTC).

## 3. Raspberry Pi

1. Flash **Raspberry Pi OS Lite (64-bit)** with Raspberry Pi Imager. In its settings, set Wi-Fi, a username and enable SSH.
2. Connect the Pi to the TV (mini-HDMI to HDMI) and power it up.
3. SSH in, copy `pi/setup-kiosk.sh` onto the Pi, and run:
   ```
   bash setup-kiosk.sh https://<user>.github.io/<repo>/
   sudo reboot
   ```
The Pi boots straight into the calendar. It reboots nightly at 3:30am, and Chromium relaunches itself if it crashes. To turn the TV off overnight, uncomment the two `cec-ctl` lines in `sudo crontab -e`.

## Everyday changes

- **Monthly flyer:** upload `site/assets/flyer-2026-11.png` (year-month). It's used automatically for that month, with `flyer.png` as the fallback. If neither exists, the timeline widens to fill the space. A portrait image about 760×990 works best.
- **Facts and quotes:** edit the text files in `content/`. They're picked up on the next run.
- **Slide timing, hours shown, refresh rate:** see the `config` block at the top of the `<script>` in `index.html`.

## Previewing / testing

Open the site with URL options:

- `?slide=week` keeps one screen up (`month`, `week` or `today`).
- `?now=2026-10-07T10:20` pretends it's a different date and time.

To run locally: `cd site && python3 -m http.server`, then open `http://localhost:8000/?now=2026-10-07T10:20`.

## Notes for the Pi Zero 2 W

- All motion uses `transform`/`opacity` only, so the GPU does the work. The backgrounds drift slowly, slides fade and rise in, and the weather icon floats.
- The page re-checks `data.json` every 30 minutes and only re-draws when it changed.
- If an update fails (e.g. Planning Center is down), the previous site stays live. A small "Data last updated…" note appears if the data is more than 36 hours old.
