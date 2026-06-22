# Contributing

Thanks for helping Cursor News.

## Local Setup

```bash
uv sync --python 3.10 --extra dev
uv run pytest
```

For a manual pipeline check:

```bash
uv run cursor-news ingest --once
uv run cursor-news tick --publish-gcp
```

## Rules

- Keep changes small and boring.
- Prefer RSS and structured data over scraping rendered pages.
- Do not commit generated audio, SQLite databases, local models, `.env`, GCP
  credentials, Android signing keys or Play Store service account files.
- French bulletins must use French articles only.
- English bulletins must use English articles only.
- Add one focused test when changing selection, filtering, scheduling or
  publishing logic.

## Useful Areas

- `config/sources.yml`: RSS source list
- `config/schedule.yml`: bulletin topics and languages
- `src/cursor_news/article_filter.py`: article rejection rules
- `src/cursor_news/pipeline.py`: selection and generation flow
- `deploy/gcp-player/`: public web UI
- `android/`: Android and Android Auto app
