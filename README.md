# Cursor News

Open-source prototype for an automated local news radio.

Cursor News ingests RSS feeds, stores articles in SQLite, builds topic-based
radio bulletins with a local LLM, renders spoken MP3 files, and publishes a web
player plus article archive to Google Cloud Storage / Cloud Run.

Public instance: https://cursor.fragniere.li/

## What It Does

- RSS-first news ingestion for Suisse romande, Valais, Switzerland,
  international news, UN-relevant news, English international news and global
  security.
- Local article archive with deduplication, read/unread state and filters.
- Hourly topic bulletins, around 8 minutes when enough articles are available.
- French bulletins use French articles only; English bulletins use English
  articles only.
- Online Edge TTS voices by default, with local TTS alternatives kept available.
- MP3 output in mono 64 kbps to keep storage and bandwidth low.
- Web UI with current flash, latest flash by topic, transcripts and archives.
- Native Android app with Android Auto media support.

## Architecture

```text
RSS feeds -> SQLite -> article filters -> local LLM -> transcript
                                               |
                                               v
                                      TTS -> MP3 -> GCS
                                                       |
                                                       v
                                      Cloud Run web + Android app
```

The production target is intentionally boring: one Ubuntu laptop runs the
pipeline, then uploads static JSON and MP3 files. Cloud Run only serves the UI.

## Requirements

- Python 3.10, managed with `uv`
- `ffmpeg`
- Ollama for local LLM generation
- Google Cloud CLI when publishing to GCP
- Android Studio / SDK only for Android builds

Current production LLM on the laptop server:

```bash
ollama pull gemma3:12b
```

## Quick Start On Windows

```cmd
scripts\setup_windows.cmd
scripts\run_server.cmd
```

In a second terminal:

```cmd
scripts\run_worker.cmd
```

Local UI: `http://localhost:8000`

## Ubuntu Server

Recommended deployment path for the always-on laptop:

```bash
bash scripts/bootstrap_ubuntu.sh
gcloud auth login
gcloud config set project cursor-news-radio-20260517
ollama pull gemma3:12b
bash scripts/run_tick_ubuntu.sh
bash scripts/install_systemd_ubuntu.sh
```

The systemd user timer runs one tick every hour. Each tick does a safe
`git pull --ff-only` when the working tree is clean, ingests news, generates the
needed bulletin buffer, renders audio and publishes the public files.

Useful server commands:

```bash
systemctl --user status cursor-news-tick.timer --no-pager
journalctl --user -u cursor-news-tick.service -n 120 --no-pager
bash scripts/check_ubuntu_server.sh
```

Full notes: `UBUNTU_SERVER_SETUP.md`

## Android

Debug build:

```cmd
scripts\build_android_debug.cmd
```

Play Store bundle:

```cmd
scripts\build_android_release.cmd
```

Publishing notes: `ANDROID_APP.md` and `PLAY_STORE_PUBLISHING.md`

## Configuration

Copy `.env.example` to `.env` and edit local values:

```bash
cp .env.example .env
```

Important rule for open-source work: never commit `.env`, GCP credentials,
Android signing keys, Play service account JSON, generated audio, local models
or SQLite data. They are ignored by `.gitignore`.

## Project Layout

```text
src/cursor_news/        Python app, pipeline, web API and publishers
config/                 RSS sources and bulletin schedule
deploy/gcp-player/      Cloud Run static web player
android/                Native Android app and Play metadata
scripts/                Windows and Ubuntu helper scripts
tests/                  Unit and integration tests
```

## Development

```bash
uv sync --python 3.10 --extra dev
uv run pytest
uv run cursor-news ingest --once
uv run cursor-news tick --publish-gcp
```

Keep changes small. This project is meant to run unattended on modest CPU-only
hardware.

## License

MIT. See `LICENSE`.
