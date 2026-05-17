from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .article_filter import is_sports_text
from .models import Article, ArticleInput, AudioResult, BulletinDraft, FeedSource, StyleSlot


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL UNIQUE,
    region TEXT NOT NULL DEFAULT 'general',
    priority INTEGER NOT NULL DEFAULT 50,
    interval_minutes INTEGER NOT NULL DEFAULT 5,
    max_entries INTEGER NOT NULL DEFAULT 20,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_etag TEXT,
    last_modified TEXT,
    last_checked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    url_hash TEXT NOT NULL UNIQUE,
    published_at TEXT,
    scraped_at TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    is_sports INTEGER NOT NULL DEFAULT 0,
    used_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status, published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);

CREATE TABLE IF NOT EXISTS bulletins (
    id TEXT PRIMARY KEY,
    slot_start TEXT NOT NULL UNIQUE,
    style_key TEXT NOT NULL,
    style_label TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    transcript TEXT NOT NULL,
    status TEXT NOT NULL,
    audio_path TEXT,
    audio_mime_type TEXT,
    duration_seconds REAL,
    warnings TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bulletin_articles (
    bulletin_id TEXT NOT NULL REFERENCES bulletins(id) ON DELETE CASCADE,
    article_id INTEGER NOT NULL REFERENCES articles(id),
    PRIMARY KEY (bulletin_id, article_id)
);

CREATE TABLE IF NOT EXISTS audio_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bulletin_id TEXT NOT NULL REFERENCES bulletins(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    duration_seconds REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    message TEXT
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def init(self) -> None:
        with self.connect() as con:
            con.executescript(SCHEMA)
            _migrate(con)

    def upsert_source(self, source: FeedSource) -> int:
        now = utc_now()
        with self.connect() as con:
            existing = con.execute(
                "SELECT id FROM sources WHERE url = ? OR name = ? ORDER BY CASE WHEN url = ? THEN 0 ELSE 1 END LIMIT 1",
                (source.url, source.name, source.url),
            ).fetchone()
            values = {
                **asdict(source),
                "enabled": 1 if source.enabled else 0,
                "created_at": now,
                "updated_at": now,
            }
            if existing:
                con.execute(
                    """
                    UPDATE sources
                    SET name = :name,
                        url = :url,
                        region = :region,
                        priority = :priority,
                        interval_minutes = :interval_minutes,
                        max_entries = :max_entries,
                        enabled = :enabled,
                        updated_at = :updated_at
                    WHERE id = :id
                    """,
                    {**values, "id": int(existing["id"])},
                )
                return int(existing["id"])
            con.execute(
                """
                INSERT INTO sources (name, url, region, priority, interval_minutes, max_entries, enabled, created_at, updated_at)
                VALUES (:name, :url, :region, :priority, :interval_minutes, :max_entries, :enabled, :created_at, :updated_at)
                """,
                values,
            )
            row = con.execute("SELECT id FROM sources WHERE url = ?", (source.url,)).fetchone()
            return int(row["id"])

    def source_cache(self, name: str) -> dict[str, str | None]:
        with self.connect() as con:
            row = con.execute(
                "SELECT last_etag, last_modified FROM sources WHERE name = ?",
                (name,),
            ).fetchone()
        if not row:
            return {"last_etag": None, "last_modified": None}
        return {"last_etag": row["last_etag"], "last_modified": row["last_modified"]}

    def update_source_fetch_state(self, source_name: str, etag: str | None, modified: str | None) -> None:
        with self.connect() as con:
            con.execute(
                """
                UPDATE sources
                SET last_etag = COALESCE(?, last_etag),
                    last_modified = COALESCE(?, last_modified),
                    last_checked_at = ?,
                    updated_at = ?
                WHERE name = ?
                """,
                (etag, modified, utc_now(), utc_now(), source_name),
            )

    def upsert_article(self, article: ArticleInput) -> tuple[int | None, bool]:
        now = utc_now()
        url_hash = canonical_hash(article.url)
        is_sports = 1 if is_sports_text(article.title, article.summary, article.content) else 0
        with self.connect() as con:
            source = con.execute("SELECT id FROM sources WHERE name = ?", (article.source_name,)).fetchone()
            if not source:
                raise ValueError(f"Unknown source: {article.source_name}")
            cur = con.execute(
                """
                INSERT OR IGNORE INTO articles
                    (source_id, title, url, url_hash, published_at, scraped_at, summary, content, is_sports, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(source["id"]),
                    article.title,
                    article.url,
                    url_hash,
                    article.published_at,
                    now,
                    article.summary,
                    article.content,
                    is_sports,
                    now,
                    now,
                ),
            )
            if cur.rowcount == 0:
                con.execute(
                    """
                    UPDATE articles
                    SET title = ?,
                        published_at = COALESCE(?, published_at),
                        summary = ?,
                        content = ?,
                        is_sports = ?,
                        scraped_at = ?,
                        updated_at = ?
                    WHERE url_hash = ?
                    """,
                    (
                        article.title,
                        article.published_at,
                        article.summary,
                        article.content,
                        is_sports,
                        now,
                        now,
                        url_hash,
                    ),
                )
                row = con.execute("SELECT id FROM articles WHERE url_hash = ?", (url_hash,)).fetchone()
                return (int(row["id"]) if row else None, False)
            row = con.execute("SELECT id FROM articles WHERE url_hash = ?", (url_hash,)).fetchone()
            return int(row["id"]), True

    def list_candidate_articles(self, limit: int) -> list[Article]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT a.id, s.name AS source_name, a.title, a.url, a.published_at, a.summary, a.content, s.priority
                FROM articles a
                JOIN sources s ON s.id = a.source_id
                WHERE a.status = 'new'
                  AND a.is_sports = 0
                ORDER BY s.priority DESC, COALESCE(a.published_at, a.created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            Article(
                id=int(row["id"]),
                source_name=row["source_name"],
                title=row["title"],
                url=row["url"],
                published_at=row["published_at"],
                summary=row["summary"],
                content=row["content"],
                priority=int(row["priority"]),
            )
            for row in rows
        ]

    def list_recent_articles(self, limit: int) -> list[Article]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT a.id, s.name AS source_name, a.title, a.url, a.published_at, a.summary, a.content, s.priority
                FROM articles a
                JOIN sources s ON s.id = a.source_id
                WHERE a.is_sports = 0
                ORDER BY COALESCE(a.published_at, a.created_at) DESC, a.used_count ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            Article(
                id=int(row["id"]),
                source_name=row["source_name"],
                title=row["title"],
                url=row["url"],
                published_at=row["published_at"],
                summary=row["summary"],
                content=row["content"],
                priority=int(row["priority"]),
            )
            for row in rows
        ]

    def bulletin_exists(self, slot_start: str) -> bool:
        with self.connect() as con:
            row = con.execute("SELECT 1 FROM bulletins WHERE slot_start = ?", (slot_start,)).fetchone()
        return row is not None

    def create_bulletin(
        self,
        bulletin_id: str,
        slot_start: str,
        style: StyleSlot,
        draft: BulletinDraft,
        articles: list[Article],
        status: str = "draft",
    ) -> None:
        now = utc_now()
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO bulletins
                    (id, slot_start, style_key, style_label, title, summary, transcript, status, warnings, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bulletin_id,
                    slot_start,
                    style.key,
                    style.label,
                    draft.title,
                    draft.summary,
                    draft.transcript,
                    status,
                    _json_list(draft.warnings),
                    now,
                    now,
                ),
            )
            for article in articles:
                con.execute(
                    "INSERT OR IGNORE INTO bulletin_articles (bulletin_id, article_id) VALUES (?, ?)",
                    (bulletin_id, article.id),
                )
                con.execute(
                    "UPDATE articles SET status = 'used', used_count = used_count + 1, updated_at = ? WHERE id = ?",
                    (now, article.id),
                )

    def mark_bulletin_ready(self, bulletin_id: str, audio: AudioResult) -> None:
        now = utc_now()
        with self.connect() as con:
            con.execute(
                """
                UPDATE bulletins
                SET status = 'ready',
                    audio_path = ?,
                    audio_mime_type = ?,
                    duration_seconds = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (str(audio.path), audio.mime_type, audio.duration_seconds, now, bulletin_id),
            )
            con.execute(
                """
                INSERT INTO audio_assets (bulletin_id, kind, path, mime_type, duration_seconds, created_at)
                VALUES (?, 'main', ?, ?, ?, ?)
                """,
                (bulletin_id, str(audio.path), audio.mime_type, audio.duration_seconds, now),
            )

    def mark_bulletin_error(self, bulletin_id: str, message: str) -> None:
        with self.connect() as con:
            con.execute(
                "UPDATE bulletins SET status = 'error', error = ?, updated_at = ? WHERE id = ?",
                (message, utc_now(), bulletin_id),
            )

    def current_bulletin(self, now: datetime | None = None) -> dict | None:
        now = now or datetime.now(timezone.utc)
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT * FROM bulletins
                WHERE status = 'ready'
                ORDER BY slot_start DESC
                LIMIT 200
                """
            ).fetchall()
        for row in rows:
            slot_start = _parse_datetime(row["slot_start"])
            if slot_start and slot_start <= now:
                return self.bulletin_by_id(str(row["id"]))
        return None

    def bulletin_by_id(self, bulletin_id: str) -> dict | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM bulletins WHERE id = ?", (bulletin_id,)).fetchone()
            if not row:
                return None
            sources = con.execute(
                """
                SELECT a.title, a.url, s.name AS source_name
                FROM bulletin_articles ba
                JOIN articles a ON a.id = ba.article_id
                JOIN sources s ON s.id = a.source_id
                WHERE ba.bulletin_id = ?
                ORDER BY s.priority DESC, a.published_at DESC
                """,
                (bulletin_id,),
            ).fetchall()
        result = dict(row)
        result["sources"] = [dict(item) for item in sources]
        return result

    def bulletin_history(self, limit: int = 12) -> list[dict]:
        with self.connect() as con:
            rows = con.execute(
                """
                SELECT id, slot_start, style_label, title, summary, transcript, audio_path, audio_mime_type, duration_seconds, created_at
                FROM bulletins
                WHERE status = 'ready'
                ORDER BY slot_start DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def article_archive(self, limit: int = 50, include_sports: bool = True) -> list[dict]:
        where = "" if include_sports else "WHERE a.is_sports = 0"
        with self.connect() as con:
            rows = con.execute(
                f"""
                SELECT a.id,
                       s.name AS source_name,
                       a.title,
                       a.url,
                       a.published_at,
                       a.scraped_at,
                       a.status,
                       a.is_sports,
                       a.used_count
                FROM articles a
                JOIN sources s ON s.id = a.source_id
                {where}
                ORDER BY COALESCE(a.published_at, a.created_at) DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def status_snapshot(self) -> dict:
        with self.connect() as con:
            counts = {
                row["status"]: int(row["count"])
                for row in con.execute("SELECT status, COUNT(*) AS count FROM articles GROUP BY status").fetchall()
            }
            archive_counts = con.execute(
                """
                SELECT COUNT(*) AS total,
                       SUM(CASE WHEN is_sports = 1 THEN 1 ELSE 0 END) AS sports,
                       SUM(CASE WHEN is_sports = 0 THEN 1 ELSE 0 END) AS editorial
                FROM articles
                """
            ).fetchone()
            bulletin_counts = {
                row["status"]: int(row["count"])
                for row in con.execute("SELECT status, COUNT(*) AS count FROM bulletins GROUP BY status").fetchall()
            }
            source_count = con.execute("SELECT COUNT(*) AS count FROM sources WHERE enabled = 1").fetchone()["count"]
            last_run = con.execute(
                "SELECT kind, status, started_at, ended_at, message FROM pipeline_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return {
            "articles": counts,
            "archive": {
                "total": int(archive_counts["total"] or 0),
                "sports": int(archive_counts["sports"] or 0),
                "editorial": int(archive_counts["editorial"] or 0),
            },
            "bulletins": bulletin_counts,
            "enabled_sources": int(source_count),
            "last_run": dict(last_run) if last_run else None,
        }

    def start_run(self, kind: str) -> int:
        with self.connect() as con:
            cur = con.execute(
                "INSERT INTO pipeline_runs (kind, status, started_at) VALUES (?, 'running', ?)",
                (kind, utc_now()),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, message: str = "") -> None:
        with self.connect() as con:
            con.execute(
                "UPDATE pipeline_runs SET status = ?, ended_at = ?, message = ? WHERE id = ?",
                (status, utc_now(), message, run_id),
            )


def _json_list(items: list[str]) -> str:
    import json

    return json.dumps(items, ensure_ascii=True)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _migrate(con: sqlite3.Connection) -> None:
    article_columns = {row["name"] for row in con.execute("PRAGMA table_info(articles)").fetchall()}
    if "is_sports" not in article_columns:
        con.execute("ALTER TABLE articles ADD COLUMN is_sports INTEGER NOT NULL DEFAULT 0")
    rows = con.execute("SELECT id, title, summary, content FROM articles").fetchall()
    for row in rows:
        con.execute(
            "UPDATE articles SET is_sports = ? WHERE id = ?",
            (
                1 if is_sports_text(row["title"], row["summary"], row["content"]) else 0,
                row["id"],
            ),
        )
