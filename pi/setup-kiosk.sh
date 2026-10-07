#!/usr/bin/env bash
# One-time setup for a Raspberry Pi Zero 2 W running Raspberry Pi OS Lite (64-bit).
# Usage:  bash setup-kiosk.sh https://YOUR-USER.github.io/YOUR-REPO/
set -euo pipefail

URL="${1:?Pass your GitHub Pages URL, e.g. bash setup-kiosk.sh https://me.github.io/smart-calendar/}"
USER_NAME="$(id -un)"

echo "==> Installing packages"
sudo apt-get update
sudo apt-get install -y --no-install-recommends cage v4l-utils fonts-open-sans
# The Chromium package name differs between OS releases
sudo apt-get install -y --no-install-recommends chromium || sudo apt-get install -y --no-install-recommends chromium-browser
CHROME="$(command -v chromium || command -v chromium-browser)"

echo "==> Writing kiosk launcher"
cat > "$HOME/kiosk.sh" <<EOF
#!/usr/bin/env bash
# Relaunch Chromium if it ever exits or crashes
while true; do
  "$CHROME" --kiosk --incognito --noerrdialogs --disable-infobars \\
    --ozone-platform=wayland --disable-features=Translate,MediaRouter \\
    --disable-session-crashed-bubble --check-for-update-interval=31536000 \\
    --renderer-process-limit=1 --disk-cache-size=1 \\
    "$URL"
  sleep 3
done
EOF
chmod +x "$HOME/kiosk.sh"

echo "==> Auto-login on the console and start the kiosk"
sudo raspi-config nonint do_boot_behaviour B2   # console autologin
if ! grep -q kiosk.sh "$HOME/.bash_profile" 2>/dev/null; then
  cat >> "$HOME/.bash_profile" <<'EOF'
# start the calendar kiosk on the physical console only (not over SSH)
if [ -z "$SSH_CONNECTION" ] && [ "$(tty)" = "/dev/tty1" ]; then
  exec cage -s -- "$HOME/kiosk.sh"
fi
EOF
fi

echo "==> Nightly reboot (3:30am) and optional TV power schedule"
CRON_TMP="$(mktemp)"
sudo crontab -l 2>/dev/null | grep -v -e 'smart-calendar' > "$CRON_TMP" || true
cat >> "$CRON_TMP" <<'EOF'
30 3 * * * /sbin/reboot  # smart-calendar
# Uncomment to turn the TV off at 9pm and on at 7am over HDMI-CEC (if your TV supports it):
# 0 21 * * * cec-ctl -d /dev/cec0 --playback --to 0 --standby       # smart-calendar
# 0 7  * * * cec-ctl -d /dev/cec0 --playback --to 0 --image-view-on # smart-calendar
EOF
sudo crontab "$CRON_TMP"; rm -f "$CRON_TMP"

echo "==> Hide the console cursor/blanking"
CMDLINE=/boot/firmware/cmdline.txt
if [ -f "$CMDLINE" ] && ! grep -q consoleblank "$CMDLINE"; then
  sudo sed -i '1 s/$/ consoleblank=0 vt.global_cursor_default=0/' "$CMDLINE"
fi

echo "Done for $USER_NAME. Reboot with: sudo reboot"
