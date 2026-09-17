from pathlib import Path
from types import SimpleNamespace

import feedparser
import httpx
import pytest

from cursor_news.database import Database
from cursor_news.ingest import FeedIngestor, _entry_date
from cursor_news.models import FeedSource
from cursor_news.sources import load_sources


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


def test_rss_date_uses_utc_not_server_timezone():
    parsed = feedparser.parse('''<rss version="2.0"><channel><item>
        <pubDate>Thu, 17 Sep 2026 12:00:00 +0200</pubDate>
        </item></channel></rss>''')
    assert _entry_date(parsed.entries[0]) == "2026-09-17T10:00:00+00:00"


@pytest.mark.parametrize("raw, expected", [
    ("2026-09-17T12:00:00+02:00", "2026-09-17T10:00:00+00:00"),
    ("2026-09-17T10:00:00Z", "2026-09-17T10:00:00+00:00"),
    ("Thu, 17 Sep 2026 10:00:00", "2026-09-17T10:00:00+00:00"),
    ("not a date", None),
])
def test_rss_raw_date_fallback(raw, expected):
    assert _entry_date(SimpleNamespace(published=raw)) == expected


def test_future_rss_date_is_clamped_on_ingestion(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("cursor_news.database.utc_now", lambda: "2026-09-17T08:00:00+00:00")
    db = Database(tmp_path / "db.sqlite3")
    db.init()
    source = FeedSource(name="Fixture", url="https://example.test/rss", region="english")
    db.upsert_source(source)
    rss = '''<rss version="2.0"><channel><item>
        <title>A new public transport service opens</title>
        <link>https://example.test/news</link>
        <pubDate>Mon, 07 Dec 2026 09:09:18 +0000</pubDate>
        <description>The city announces a new service.</description>
        </item></channel></rss>'''
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=rss))
    ingestor = FeedIngestor(db, tmp_path / "sources.yml")
    with httpx.Client(transport=transport) as client:
        assert ingestor._ingest_source(client, source)["new_articles"] == 1
        assert db.article_archive()[0]["published_at"] == "2026-09-17T08:00:00+00:00"
        assert db.exclude_article("https://example.test/news")
        assert ingestor._ingest_source(client, source)["new_articles"] == 0
        assert db.article_archive() == []


def test_configured_exclusion_applies_even_when_feed_is_not_modified(tmp_path, monkeypatch):
    from cursor_news.models import ArticleInput

    monkeypatch.setattr("cursor_news.ingest.shutil.which", lambda name: None)
    sources = load_sources(Path("config/sources.yml"))
    source = next(s for s in sources if s.url == "https://www.fr.ch/rss.xml")
    url = "https://www.fr.ch/parlinfo/guide-parlementaire"
    assert url in source.exclude_urls
    db = Database(tmp_path / "db.sqlite3")
    db.init()
    db.upsert_source(source)
    db.upsert_article(ArticleInput(source.name, "Guide parlementaire", url, None, "Details", ""))
    ingestor = FeedIngestor(db, Path("config/sources.yml"))
    assert ingestor._entry_to_article(source, SimpleNamespace(title="Guide parlementaire", link=url + "#documents")) is None
    transport = httpx.MockTransport(lambda request: httpx.Response(304))
    with httpx.Client(transport=transport) as client:
        assert ingestor._ingest_source(client, source)["status"] == "not_modified"
    assert db.article_archive() == []
    assert db.list_recent_articles(10) == []
