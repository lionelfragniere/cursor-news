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


def test_export_site_news_deduplicates_same_story_across_sources(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    settings = load_settings()
    db = Database(settings.database_path)
    db.init()
    for name, priority in [("RTN - Région", 140), ("RJB - Région", 138), ("RFJ - Région", 136)]:
        db.upsert_source(FeedSource(name=name, url=f"https://example.test/{priority}/rss", region="suisse-romande", priority=priority))
        db.upsert_article(
            ArticleInput(
                source_name=name,
                title="Slamer en forêt pour mieux admirer la nature",
                url=f"https://example.test/{priority}/nature",
                published_at="2026-05-18T16:00:00+02:00",
                summary="La Fête de la nature démarre ce mercredi un peu partout en Suisse romande.",
                content="",
            )
        )

    output = tmp_path / "site" / "news.json"
    payload = export_site_news(settings, output, limit=20)

    assert payload["count"] == 1
    assert payload["articles"][0]["source_name"] == "RTN - Région"


def test_export_site_news_keeps_english_web_only(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    settings = load_settings()
    db = Database(settings.database_path)
    db.init()
    db.upsert_source(FeedSource(name="UN News", url="https://news.un.org/rss", region="english", priority=45))
    db.upsert_source(FeedSource(name="RTN", url="https://example.test/rss", region="suisse-romande", priority=140))
    db.upsert_article(
        ArticleInput(
            source_name="UN News",
            title="UN Secretary-General calls for renewed diplomacy",
            url="https://news.un.org/en/story/1",
            published_at="2026-05-19T08:00:00+00:00",
            summary="The United Nations Secretary-General called for renewed diplomatic efforts.",
            content="",
        )
    )
    db.upsert_article(
        ArticleInput(
            source_name="RTN",
            title="Une actualité romande",
            url="https://example.test/news",
            published_at="2026-05-19T09:00:00+00:00",
            summary="Une information locale.",
            content="",
        )
    )

    android_payload = export_site_news(settings, tmp_path / "android.json", limit=20)
    web_payload = export_site_news(settings, tmp_path / "web.json", limit=20, include_english=True)

    assert "english" not in android_payload["regions"]
    assert "english" in web_payload["regions"]
    assert [item["source_name"] for item in android_payload["articles"]] == ["RTN"]
    assert {item["source_name"] for item in web_payload["articles"]} == {"RTN", "UN News"}
