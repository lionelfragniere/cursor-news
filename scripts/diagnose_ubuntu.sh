#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

export PATH="$HOME/.local/bin:$PATH"
export PYTHONUTF8=1

echo "== Cursor News diagnostic =="
echo "Project: $ROOT_DIR"
echo

echo "== Time =="
date
TZ=UTC date
TZ=Europe/Zurich date
echo

echo "== Git =="
git rev-parse --short HEAD 2>/dev/null || true
git status -sb 2>/dev/null || true
echo

echo "== Tools =="
for tool in uv ffmpeg gcloud ollama systemctl journalctl; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf "%-10s %s\n" "$tool" "$(command -v "$tool")"
  else
    printf "%-10s missing\n" "$tool"
  fi
done
echo

echo "== Sanitized .env =="
if [ -f .env ]; then
  grep -E '^(CURSOR_NEWS_|LLM_PROVIDER|OLLAMA_|TTS_ENGINE|EDGE_TTS_|FFMPEG_PATH|GCLOUD_PATH|GCP_)' .env \
    | sed -E 's/(TOKEN|PASSWORD|SECRET|KEY)=.*/\1=***/I' || true
else
  echo ".env missing"
fi
echo

echo "== systemd timer =="
systemctl --user status cursor-news-tick.timer --no-pager || true
systemctl --user list-timers cursor-news-tick.timer --all || true
echo

echo "== systemd service =="
systemctl --user status cursor-news-tick.service --no-pager || true
echo

echo "== Recent tick journal =="
journalctl --user -u cursor-news-tick.service --since "today" -n 260 --no-pager || true
echo

echo "== Running related processes =="
pgrep -af 'cursor-news|ollama|ffmpeg|edge_tts|python' || true
echo

echo "== Cursor News DB status =="
uv run --python 3.10 cursor-news status || true
echo

echo "== Latest DB rows =="
uv run --python 3.10 python - <<'PY' || true
from datetime import datetime
from zoneinfo import ZoneInfo

from cursor_news.settings import load_settings
from cursor_news.database import Database

settings = load_settings()
db = Database(settings.database_path)
db.init()
zurich = ZoneInfo("Europe/Zurich")

def fmt(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone(zurich).isoformat(timespec="minutes")
    except Exception:
        return str(value)

with db.connect() as con:
    print("Latest bulletins:")
    for row in con.execute(
        """
        SELECT slot_start, status, style_label, title, error, updated_at
        FROM bulletins
        ORDER BY slot_start DESC
        LIMIT 12
        """
    ):
        print(f"- {fmt(row['slot_start'])} | {row['status']} | {row['style_label']} | {row['title']} | {row['error'] or ''}")

    print("\nLatest articles:")
    for row in con.execute(
        """
        SELECT a.published_at, a.scraped_at, s.name AS source_name, a.title, a.status, a.is_sports
        FROM articles a
        JOIN sources s ON s.id = a.source_id
        ORDER BY COALESCE(a.published_at, a.scraped_at) DESC
        LIMIT 12
        """
    ):
        date = fmt(row["published_at"] or row["scraped_at"])
        kind = "sport" if row["is_sports"] else row["status"]
        print(f"- {date} | {row['source_name']} | {kind} | {row['title'][:110]}")
PY
echo

echo "== GCP current objects =="
if command -v gcloud >/dev/null 2>&1; then
  gcloud storage ls -L \
    gs://cursor-news-radio-20260517-audio/current/news.json \
    gs://cursor-news-radio-20260517-audio/current/manifest.json \
    gs://cursor-news-radio-20260517-audio/current/live.mp3 \
    --project cursor-news-radio-20260517 || true
else
  echo "gcloud missing"
fi
