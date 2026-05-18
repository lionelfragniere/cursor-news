#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== Cursor News bootstrap Ubuntu =="
echo "Projet: $ROOT_DIR"

sudo apt-get update
sudo apt-get install -y \
  ca-certificates \
  curl \
  ffmpeg \
  git \
  gnupg \
  lsb-release \
  unzip \
  build-essential

if ! command -v uv >/dev/null 2>&1; then
  echo "== Installation uv =="
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "== Installation Google Cloud CLI =="
  curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y google-cloud-cli
fi

if ! command -v ollama >/dev/null 2>&1; then
  echo "== Installation Ollama =="
  curl -fsSL https://ollama.com/install.sh | sh
fi

echo "== Installation Python 3.10 via uv =="
uv python install 3.10
uv sync --python 3.10

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ".env créé depuis .env.example. Vérifie les variables GCP_* avant le premier tick."
fi

if grep -Eq '^FFMPEG_PATH=.*\\.*ffmpeg\.exe' .env 2>/dev/null; then
  cp .env ".env.backup.$(date +%Y%m%d%H%M%S)"
  sed -i 's|^FFMPEG_PATH=.*|FFMPEG_PATH=|' .env
  echo "FFMPEG_PATH Windows détecté dans .env; Ubuntu utilisera ffmpeg depuis le PATH."
fi

if grep -Eq '^GCLOUD_PATH=.*\.cmd' .env 2>/dev/null; then
  cp .env ".env.backup.$(date +%Y%m%d%H%M%S)"
  sed -i 's|^GCLOUD_PATH=.*|GCLOUD_PATH=gcloud|' .env
  echo "GCLOUD_PATH Windows détecté dans .env; Ubuntu utilisera gcloud depuis le PATH."
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload >/dev/null 2>&1 || true
fi

cat <<'MSG'

Bootstrap terminé.

Étapes manuelles à faire une fois:
  gcloud auth login
  gcloud config set project cursor-news-radio-20260517
  ollama pull qwen3:14b

Puis tester:
  scripts/run_tick_ubuntu.sh

MSG
