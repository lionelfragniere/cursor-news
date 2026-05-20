#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_DIR="$HOME/.config/systemd/user"
RUNNER_DIR="$HOME/.local/bin"
RUNNER_PATH="$RUNNER_DIR/cursor-news-tick-runner"
mkdir -p "$SYSTEMD_DIR"
mkdir -p "$RUNNER_DIR"

cat > "$RUNNER_PATH" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$ROOT_DIR"
exec bash "$ROOT_DIR/scripts/run_tick_ubuntu.sh"
EOF
chmod +x "$RUNNER_PATH"

cat > "$SYSTEMD_DIR/cursor-news-tick.service" <<EOF
[Unit]
Description=Cursor News pipeline tick
After=network-online.target

[Service]
Type=oneshot
Environment=CURSOR_NEWS_AUTO_GIT_PULL=1
ExecStart=$RUNNER_PATH
TimeoutStartSec=1800
Nice=5
IOSchedulingClass=best-effort
IOSchedulingPriority=6
EOF

cat > "$SYSTEMD_DIR/cursor-news-tick.timer" <<'EOF'
[Unit]
Description=Run Cursor News every hour

[Timer]
OnBootSec=2min
OnCalendar=*:00:00
Persistent=true
RandomizedDelaySec=20
Unit=cursor-news-tick.service

[Install]
WantedBy=timers.target
EOF

systemctl --user reset-failed cursor-news-tick.service cursor-news-tick.timer >/dev/null 2>&1 || true
systemctl --user daemon-reload
systemctl --user enable --now cursor-news-tick.timer

if command -v loginctl >/dev/null 2>&1; then
  sudo loginctl enable-linger "$USER"
fi

cat <<'MSG'

Timer installé.

Commandes utiles:
  systemctl --user status cursor-news-tick.timer
  systemctl --user list-timers cursor-news-tick.timer
  journalctl --user -u cursor-news-tick.service -n 120 --no-pager

Auto-update:
  Le tick fait un git pull --ff-only avant chaque scrape si le repo est propre.
  Pour le couper: systemctl --user edit cursor-news-tick.service
  puis ajoute Environment=CURSOR_NEWS_AUTO_GIT_PULL=0 dans [Service].

MSG
