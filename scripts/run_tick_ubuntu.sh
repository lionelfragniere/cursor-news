#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PATH="$HOME/.local/bin:$PATH"
export PYTHONUTF8=1

uv run --python 3.10 cursor-news tick --publish-gcp --news-limit 500
