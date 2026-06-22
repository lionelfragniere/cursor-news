# Privacy

Cursor News is designed to keep the heavy processing on the server owner side.

## Web App

The public web app loads news JSON and MP3 files from the project hosting. It
stores read/unread state and filter preferences in the browser only.

## Android App

The Android app loads the same public news JSON and MP3 files. It stores read
state and filter preferences locally on the device. It does not require an
account.

## Server

The server ingests public RSS feeds, stores articles in SQLite and uploads only
public bulletin assets to GCP.

## Third Parties

Depending on deployment settings, the project may use:

- Google Cloud Storage / Cloud Run for public hosting
- Microsoft Edge TTS voices for speech generation
- Ollama locally for text generation

Do not put private information or credentials in RSS source config, generated
transcripts or public bucket files.
