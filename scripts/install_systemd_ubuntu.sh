#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

SYSTEMD_ROOT_DIR="${ROOT_DIR//\\/\\\\}"
SYSTEMD_ROOT_DIR="${SYSTEMD_ROOT_DIR//\"/\\\"}"

cat > "$SYSTEMD_DIR/cursor-news-tick.service" <<EOF
[Unit]
Description=Cursor News pipeline tick
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory="$SYSTEMD_ROOT_DIR"
ExecStart=/usr/bin/env bash "$SYSTEMD_ROOT_DIR/scripts/run_tick_ubuntu.sh"
TimeoutStartSec=1800
Nice=5
IOSchedulingClass=best-effort
IOSchedulingPriority=6
EOF

cat > "$SYSTEMD_DIR/cursor-news-tick.timer" <<'EOF'
[Unit]
Description=Run Cursor News every ten minutes

[Timer]
OnBootSec=2min
OnCalendar=*:0/10
Persistent=true
RandomizedDelaySec=20
Unit=cursor-news-tick.service

[Install]
WantedBy=timers.target
EOF

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

MSG
