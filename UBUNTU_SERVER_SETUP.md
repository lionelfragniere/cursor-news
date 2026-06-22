# Cursor News On Ubuntu Laptop

This guide prepares an Ubuntu Desktop laptop to run Cursor News unattended.

The laptop handles:

- RSS ingestion;
- SQLite article storage;
- hourly topic bulletin generation;
- female French and English TTS voices through Edge TTS;
- MP3 generation in mono 64 kbps;
- upload of public JSON, transcripts and audio files to GCP.

## Recommended OS

Ubuntu Desktop LTS is the recommended server OS for the laptop. It is simpler
than Windows Server, friendlier than a minimal server install, and still easy to
manage over SSH.

## 1. Prepare The USB Key From Windows

From `D:\Cursor News`:

```cmd
scripts\prepare_ubuntu_usb_windows.cmd
```

The script downloads the official Ubuntu Desktop ISO and prints the local
SHA256 hash. It does not write to the USB key.

Then use Rufus or BalenaEtcher to flash the ISO and install Ubuntu on the
laptop.

## 2. Prepare Ubuntu

Keep the laptop plugged in. Disable automatic sleep in Ubuntu settings.

Optional, for a dedicated server laptop:

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Enable SSH if you want to manage it from another machine:

```bash
sudo apt update
sudo apt install -y openssh-server
sudo systemctl enable --now ssh
sudo ufw allow OpenSSH || true
```

## 3. Clone Or Copy The Project

Recommended path:

```text
~/Cursor News
```

Files worth preserving during migrations:

- `.env`
- `config/`
- `data/`, if you want the local article history

Ubuntu `.env` basics:

```env
CURSOR_NEWS_HOME=.
FFMPEG_PATH=
GCLOUD_PATH=gcloud
GCP_PROJECT_ID=cursor-news-radio-20260517
GCP_BUCKET=gs://cursor-news-radio-20260517-audio
GCP_PUBLIC_BASE_URL=https://storage.googleapis.com/cursor-news-radio-20260517-audio
TTS_ENGINE=edge
EDGE_TTS_VOICE=fr-CH-ArianeNeural
LLM_PROVIDER=ollama
OLLAMA_MODEL=gemma3:12b
OLLAMA_TIMEOUT_SECONDS=1800
```

## 4. Install Dependencies

From the project root:

```bash
bash scripts/bootstrap_ubuntu.sh
```

Then run the one-time account/model setup:

```bash
gcloud auth login
gcloud config set project cursor-news-radio-20260517
ollama pull gemma3:12b
```

## 5. Manual Tick

Run one full cycle:

```bash
bash scripts/run_tick_ubuntu.sh
```

The tick ingests RSS, updates the database, generates needed bulletins, renders
audio and publishes the public files.

Check the server:

```bash
bash scripts/check_ubuntu_server.sh
```

## 6. Hourly Automation

Install the systemd user timer:

```bash
bash scripts/install_systemd_ubuntu.sh
```

Useful commands:

```bash
systemctl --user status cursor-news-tick.timer --no-pager
systemctl --user list-timers cursor-news-tick.timer
journalctl --user -u cursor-news-tick.service -n 120 --no-pager
```

The timer runs at the start of each hour. It also performs a safe
`git pull --ff-only` before each tick when the working tree is clean.

## 7. Public Site

The public site is:

```text
https://cursor.fragniere.li/
```

Dynamic assets are published to the GCS bucket:

- `current/news.json`
- `current/manifest.json`
- `current/live.mp3`
- `bulletins/{id}.mp3`

## 8. Notes

- Keep only recent bulletins in GCP; local SQLite holds the longer article
  history.
- Do not commit `.env`, generated audio, SQLite files, Android keys or GCP
  credentials.
- If generation is too slow, lower `CURSOR_NEWS_MAX_ARTICLES` before changing
  model or architecture.
