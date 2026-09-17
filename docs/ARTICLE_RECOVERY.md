# Recover articles after downtime

RSS feeds usually expose only their most recent entries. Restarting the worker
cannot recover all the articles published while it was offline.

From the project directory on the server, inspect publication dates and initial
collection dates (not the mutable `scraped_at` timestamp):

```bash
uv run --python 3.10 python -m cursor_news.backfill \
  --start 2026-09-03 --end 2026-09-18 --audit-only
```

Dates use `Europe/Zurich`; `--end` is exclusive. The recovery tool accepts ranges
up to 31 days and operates on an existing, initialized Cursor News database.

Recover public article titles, publication dates, descriptions and source links:

```bash
uv run --python 3.10 python -m cursor_news.backfill \
  --start 2026-09-09 --end 2026-09-17
```

The command saves a consistent SQLite backup and an incremental JSON report in
`data/backfill/<UTC timestamp>/`. The report includes daily counts before and
after recovery, inserted IDs, errors and sources without a configured archive.
Keep the backup private: it contains your local article database.

Recovered records have `status=archived`: they are searchable and exportable but
excluded from both normal and fallback radio article selection. Existing URLs,
content, read/used state and publication dates are left unchanged. Re-running the
command skips existing URLs, including known RSS/archive aliases (HTTP/HTTPS,
BBC tracking parameters, Le Temps section paths, UN feed links and radio document
IDs). Normal RSS collection continues independently.

`config/backfill.yml` describes public archive indexes and supported publishers.
The importer uses four source workers with paced requests, bounded pagination,
timeouts and the existing HTTP/HTML libraries. It does not generate text or audio,
translate articles, bypass paywalls or solve access challenges. It stores public
descriptions, not the complete text of subscriber articles. Publication metadata
is required; a sitemap modification date is never used as a publication date.

To retry one publisher after inspecting the report:

```bash
uv run --python 3.10 python -m cursor_news.backfill \
  --start 2026-09-09 --end 2026-09-17 --source "RTN"
```

Partial recovery is expected when publishers have limited archives, missing date
metadata or access restrictions. A nonempty day does not establish complete
coverage, and the report cannot count articles a publisher no longer exposes.
The radio sitemap adapter follows the URL-sorted, date-prefixed regional archive;
undated older URL formats are outside its scope.

The regular tick will publish recovered records within its export limit. For an
immediate refresh after the running tick has finished, use its existing lock:

```bash
flock -n data/cache/tick.lock .venv/bin/cursor-news publish-gcp --news-limit 3000
```

The website's archive can only search the articles included in that exported
snapshot. Older recovered articles remain in SQLite even when outside the
snapshot's size limit. Recovery does not increase cloud retention or upload audio.
