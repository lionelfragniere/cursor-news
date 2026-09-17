from datetime import date

from cursor_news.backfill import ArchiveReader, article_key, article_metadata, audit, parse_date, url_date
from cursor_news.database import Database
from cursor_news.models import ArticleInput, FeedSource


def test_archive_import_is_idempotent_preserves_live_data_and_cannot_feed_radio(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    source = FeedSource("Fixture", "https://example.test/rss")
    db.upsert_source(source)
    old = ArticleInput(source.name, "Les nouvelles", "https://example.test/old", "2026-09-10T12:00:00+02:00",
                       "Un article de septembre.", "Son contenu complet.", "fr")
    old_id, created = db.upsert_article(old, archive_only=True)
    assert created
    assert db.upsert_article(old, archive_only=True) == (old_id, False)
    assert db.list_candidate_articles(50) == []
    assert db.list_recent_articles(50) == []
    assert len(db.article_archive()) == 1
    live = ArticleInput(source.name, "Titre actuel", "https://example.test/live", old.published_at,
                        "Resume actuel", "Contenu complet actuel", "fr")
    live_id, _ = db.upsert_article(live)
    stale = ArticleInput(source.name, "Ancien titre", live.url, None, "", "", "fr")
    assert db.upsert_article(stale, archive_only=True) == (live_id, False)
    current = db.list_candidate_articles(50)[0]
    assert current.title == "Titre actuel" and current.content == "Contenu complet actuel"
    counts = audit(db, date(2026, 9, 10), date(2026, 9, 12))
    assert counts["2026-09-10"]["published"] == 2
    assert counts["2026-09-11"]["published"] == 0


def test_metadata_uses_publication_date_not_modification_and_preserves_accents():
    source = FeedSource("Fixture", "https://example.test/rss")
    html = '''<html><head><meta property="og:title" content="Une école rénovée">
    <meta property="og:description" content="Les élèves retrouvent leur école.">
    <meta property="article:published_time" content="2026-09-10T23:30:00Z">
    <meta name="dateModified" content="2026-09-17T08:00:00Z">
    <link rel="canonical" href="https://example.test/news"></head></html>'''
    article = article_metadata(html, "https://example.test/news#title", source)
    assert article.title == "Une école rénovée"
    assert article.url == "https://example.test/news"
    assert article.published_at == "2026-09-10T23:30:00+00:00"
    assert article.content == article.summary == "Les élèves retrouvent leur école."
    assert article_metadata(html.replace('property="article:published_time"', 'name="dateModified"'), article.url, source) is None
    assert parse_date("nonsense") is None
    assert url_date("https://example.test/20260910-news") == date(2026, 9, 10)
    assert url_date("https://example.test/2026/09/10/news") == date(2026, 9, 10)
    radio_html = '''<meta property="og:title" content="La rentrée à Neuchâtel">
    <time itemprop="datePublished" datetime="2026-09-10T13:56"></time>
    <time itemprop="dateModified" datetime="2026-09-11T11:00"></time>'''
    assert article_metadata(radio_html, article.url, source).published_at == "2026-09-10T13:56:00+02:00"
    radio_html += '<form action="/Scripts/Modules/Customers/Login.aspx?add=1&amp;ReturnURL=/Scripts/Index.aspx?id=123"></form>'
    assert article_metadata(radio_html, "https://www.rtn.ch/rtn/Actualite/Region/story.html", source).url == "https://www.rtn.ch/Scripts/Index.aspx?id=123"


def test_sitemap_fetch_fails_per_source_and_out_of_range_articles_not_inserted(tmp_path):
    source = FeedSource("Fixture", "https://example.test/rss")
    db = Database(tmp_path / "test.sqlite3")
    db.init()
    db.upsert_source(source)
    reader = ArchiveReader(source, {"kind": "sitemap", "hosts": ["example.test"],
        "urls": ["https://example.test/sitemap.xml"], "article_pattern": "/news/"},
        date(2026, 9, 10), date(2026, 9, 11), set())
    pages = {
        "https://example.test/sitemap.xml": '<urlset><url><loc>https://example.test/news/old</loc><lastmod>2026-09-10</lastmod></url><url><loc>https://unrelated.test/news/a</loc></url></urlset>',
        "https://example.test/news/old": '<meta property="og:title" content="Old news"><meta property="article:published_time" content="2026-01-01T10:00:00Z">',
    }
    reader.fetch = pages.__getitem__
    result = reader.recover(db)
    assert result["outside_range"] == 1
    assert result["inserted"] == 0 and not result["errors"]
    assert db.article_archive() == []


def test_publisher_archive_urls_match_rss_aliases():
    pairs = [
        ("http://www.france24.com/fr/europe/story", "https://www.france24.com/fr/europe/story"),
        ("https://www.letemps.ch/articles/article", "https://www.letemps.ch/suisse/valais/article"),
        ("https://news.un.org/feed/view/en/story/2026/09/123", "https://news.un.org/en/story/2026/09/123"),
        ("https://www.bbc.co.uk/news/articles/xyz?at_medium=RSS&at_campaign=rss", "https://www.bbc.com/news/articles/xyz"),
    ]
    for left, right in pairs:
        assert article_key(left) == article_key(right)
    assert article_key("https://www.rtn.ch/Scripts/Index.aspx?id=1") != article_key("https://www.rtn.ch/Scripts/Index.aspx?id=2")
