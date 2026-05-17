from pathlib import Path

from cursor_news.models import ArticleInput, BulletinDraft, FeedSource
from cursor_news.pipeline import CursorNewsPipeline, _draft_quality_issue
from cursor_news.settings import load_settings


def test_pipeline_generates_with_template_and_tone(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("LLM_PROVIDER", "template")
    monkeypatch.setenv("TTS_ENGINE", "tone")
    monkeypatch.setenv("FFMPEG_PATH", "")
    monkeypatch.setenv("ALLOW_WAV_FALLBACK", "1")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    generated = pipeline.generate_buffer()
    assert generated
    current = pipeline.db.current_bulletin()
    assert current is not None
    assert Path(current["audio_path"]).exists()


def test_pipeline_article_selection_skips_sports(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "2")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss"))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Premier League : Xabi Alonso nommé entraîneur de Chelsea",
            url="https://example.test/sport",
            published_at="2026-05-17T12:10:00+02:00",
            summary="Le club annonce un changement de coach.",
            content="",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Une réforme de la santé est présentée",
            url="https://example.test/news",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Le Conseil fédéral détaille son projet.",
            content="",
        )
    )
    selected = pipeline._select_articles()
    assert [article.title for article in selected] == ["Une réforme de la santé est présentée"]


def test_pipeline_child_selection_skips_adult_topics(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "2")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss"))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Peut-on avoir une vie sexuelle sous antidépresseurs ?",
            url="https://example.test/adult",
            published_at="2026-05-17T12:10:00+02:00",
            summary="Un sujet santé intime.",
            content="",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Des médecins surveillent une épidémie",
            url="https://example.test/health",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Les équipes médicales suivent la situation.",
            content="",
        )
    )
    selected = pipeline._select_articles("enfant")
    assert [article.title for article in selected] == ["Des médecins surveillent une épidémie"]


def test_pipeline_child_selection_prefers_calm_articles(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "2")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss"))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Guerre en Ukraine : nouvelles attaques de drones",
            url="https://example.test/risk",
            published_at="2026-05-17T12:10:00+02:00",
            summary="La crise continue.",
            content="",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Festival de Cannes : un film récompensé",
            url="https://example.test/calm",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Une actualité culturelle.",
            content="",
        )
    )
    selected = pipeline._select_articles("enfant")
    assert [article.title for article in selected] == [
        "Festival de Cannes : un film récompensé",
        "Guerre en Ukraine : nouvelles attaques de drones",
    ]


def test_pipeline_non_anxiogene_selection_prefers_calm_articles(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "2")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss"))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Guerre en Ukraine : nouvelles attaques de drones",
            url="https://example.test/risk",
            published_at="2026-05-17T12:10:00+02:00",
            summary="La crise continue.",
            content="",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Festival de Cannes : un film récompensé",
            url="https://example.test/calm",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Une actualité culturelle.",
            content="",
        )
    )
    selected = pipeline._select_articles("non_anxiogene")
    assert [article.title for article in selected] == [
        "Festival de Cannes : un film récompensé",
        "Guerre en Ukraine : nouvelles attaques de drones",
    ]


def test_draft_quality_issue_rejects_short_llm_output():
    draft = BulletinDraft(title="Court", summary="", transcript="Trop court.")
    assert _draft_quality_issue(draft) == "LLM returned a short transcript (2 words)"


def test_draft_quality_issue_rejects_self_reported_short_output():
    draft = BulletinDraft(
        title="Court",
        summary="",
        transcript=" ".join(["mot"] * 500),
        warnings=["Le bulletin radio est trop court."],
    )
    assert _draft_quality_issue(draft) == "LLM self-reported a short transcript"
