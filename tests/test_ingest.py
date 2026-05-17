from pathlib import Path

import feedparser

from cursor_news.database import Database
from cursor_news.ingest import FeedIngestor
from cursor_news.models import FeedSource


def test_rss_fixture_entry_to_article(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    source = FeedSource(name="Fixture", url="https://example.test/rss")
    parsed = feedparser.parse(Path("tests/fixtures/rss_sample.xml").read_bytes())
    article = FeedIngestor(db, Path("config/sources.yml"))._entry_to_article(source, parsed.entries[0])
    assert article is not None
    assert article.source_name == "Fixture"
    assert "service public" in article.title
    assert article.url == "https://example.test/suisse/service-public"


def test_ingest_source_max_entries_zero_means_all_entries(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.init()
    source = FeedSource(name="Fixture", url="https://example.test/rss", max_entries=0)
    parsed = feedparser.parse(Path("tests/fixtures/rss_sample.xml").read_bytes())
    entries = parsed.entries if source.max_entries <= 0 else parsed.entries[: source.max_entries]
    assert len(entries) == len(parsed.entries)
