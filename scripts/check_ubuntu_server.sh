#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PATH="$HOME/.local/bin:$PATH"

echo "== System =="
uname -a

echo
echo "== Tools =="
for tool in uv ffmpeg gcloud ollama; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf "%-8s %s\n" "$tool" "$(command -v "$tool")"
  else
    printf "%-8s missing\n" "$tool"
  fi
done

echo
echo "== Python project =="
uv run --python 3.10 python -c "import sys; print(sys.version)"
uv run --python 3.10 cursor-news status

echo
echo "== GCP auth =="
gcloud auth list --filter=status:ACTIVE --format="value(account)" || true
gcloud config get-value project || true

echo
echo "== Timer =="
systemctl --user list-timers cursor-news-tick.timer || true
