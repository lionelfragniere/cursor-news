from pathlib import Path

from cursor_news.database import Database
from cursor_news.models import ArticleInput, FeedSource
from cursor_news.settings import load_settings
from cursor_news.site_export import export_site_news


def test_export_site_news_writes_filter_metadata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    settings = load_settings()
    db = Database(settings.database_path)
    db.init()
    db.upsert_source(FeedSource(name="RTN - Région", url="https://example.test/rss", region="suisse-romande", priority=140))
    db.upsert_article(
        ArticleInput(
            source_name="RTN - Région",
            title="Un nouveau projet culturel ouvre à Neuchâtel",
            url="https://example.test/news",
            published_at="2026-05-17T10:00:00+00:00",
            summary="Un festival local ouvre ses portes avec des ateliers pour les familles.",
            content="Culture et familles à Neuchâtel.",
        )
    )

    output = tmp_path / "site" / "news.json"
    payload = export_site_news(settings, output, limit=20)

    assert output.exists()
    assert payload["count"] == 1
    assert payload["regions"] == ["suisse-romande"]
    assert payload["articles"][0]["source_name"] == "RTN - Région"
    assert payload["articles"][0]["child_friendly"] is True
    assert "tension" in payload["articles"][0]
