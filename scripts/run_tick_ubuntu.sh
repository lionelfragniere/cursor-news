#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PATH="$HOME/.local/bin:$PATH"
export PYTHONUTF8=1

mkdir -p "$ROOT_DIR/data/cache"
LOCK_PATH="$ROOT_DIR/data/cache/tick.lock"
exec 9>"$LOCK_PATH"
if ! flock -n 9; then
  echo "Another Cursor News tick is already running; skipping this run."
  exit 0
fi

auto_git_pull() {
  if [[ "${CURSOR_NEWS_AUTO_GIT_PULL:-1}" != "1" ]]; then
    echo "Auto git pull disabled."
    return
  fi
  if ! command -v git >/dev/null 2>&1 || [[ ! -d "$ROOT_DIR/.git" ]]; then
    echo "Auto git pull skipped: git repository not found."
    return
  fi
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Auto git pull skipped: working tree has local changes."
    return
  fi

  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [[ -z "$branch" || "$branch" == "HEAD" ]]; then
    echo "Auto git pull skipped: detached HEAD."
    return
  fi

  echo "Auto git pull on branch $branch..."
  export GIT_TERMINAL_PROMPT=0
  if command -v timeout >/dev/null 2>&1; then
    if ! timeout 90s git pull --ff-only; then
      echo "Auto git pull failed or timed out; continuing tick with current code."
    fi
  elif ! git pull --ff-only; then
    echo "Auto git pull failed; continuing tick with current code."
  fi
}

auto_git_pull

uv run --python 3.10 cursor-news tick --publish-gcp --news-limit 3000
