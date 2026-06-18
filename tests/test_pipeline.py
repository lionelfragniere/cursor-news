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


def test_pipeline_article_selection_deduplicates_same_story(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "5")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    for name, priority in [("RTN - Région", 140), ("RJB - Région", 138), ("RFJ - Région", 136)]:
        pipeline.db.upsert_source(FeedSource(name=name, url=f"https://example.test/{priority}/rss", priority=priority))
        pipeline.db.upsert_article(
            ArticleInput(
                source_name=name,
                title="Slamer en forêt pour mieux admirer la nature",
                url=f"https://example.test/{priority}/nature",
                published_at="2026-05-18T16:00:00+02:00",
                summary="La Fête de la nature démarre ce mercredi un peu partout en Suisse romande.",
                content="",
            )
        )
    pipeline.db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss", priority=100))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Un nouveau train est annoncé dans le Jura",
            url="https://example.test/train",
            published_at="2026-05-18T15:00:00+02:00",
            summary="Une nouvelle liaison est présentée.",
            content="",
        )
    )

    selected = pipeline._select_articles()

    assert [article.title for article in selected] == [
        "Slamer en forêt pour mieux admirer la nature",
        "Un nouveau train est annoncé dans le Jura",
    ]


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


def test_pipeline_english_bulletin_uses_only_english_articles(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "5")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="UN News", url="https://news.un.org/rss", region="english", priority=100))
    pipeline.db.upsert_source(FeedSource(name="RFI", url="https://rfi.fr/rss", region="international", priority=100))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="UN News",
            title="UN warns of worsening humanitarian access",
            url="https://news.un.org/en/story",
            published_at="2026-05-17T12:10:00+02:00",
            summary="UN agencies call for better access to civilians.",
            content="",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="RFI",
            title="L'ONU alerte sur l'accès humanitaire",
            url="https://rfi.fr/fr/story",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Les agences demandent un meilleur accès aux civils.",
            content="",
        )
    )

    selected = pipeline._select_articles("un_relevant")

    assert selected
    assert {article.region for article in selected} == {"english"}


def test_pipeline_french_bulletin_excludes_english_articles(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "5")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="BBC", url="https://bbc.com/rss", region="english", priority=150))
    pipeline.db.upsert_source(FeedSource(name="RFI", url="https://rfi.fr/rss", region="international", priority=100))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="BBC",
            title="Major international security update",
            url="https://bbc.com/story",
            published_at="2026-05-17T12:10:00+02:00",
            summary="A global security update is published.",
            content="",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="RFI",
            title="Situation sécuritaire mondiale: nouveau point",
            url="https://rfi.fr/fr/story",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Un point francophone sur la situation sécuritaire.",
            content="",
        )
    )

    selected = pipeline._select_articles("security_world")

    assert selected
    assert all(article.region != "english" for article in selected)


def test_pipeline_french_bulletin_excludes_german_articles(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "5")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="Valais", url="https://example.test/rss", region="valais", priority=150))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Valais",
            title="Der Staatsrat informiert über neue Massnahmen",
            url="https://example.test/de",
            published_at="2026-05-17T12:10:00+02:00",
            summary="Die Regierung im Wallis stellt eine neue Regelung für die Gemeinden vor.",
            content="",
            language="de",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Valais",
            title="Le Valais présente une nouvelle mesure",
            url="https://example.test/fr",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Le canton explique son projet pour les communes.",
            content="",
            language="fr",
        )
    )

    selected = pipeline._select_articles("valais")

    assert selected
    assert [article.language for article in selected] == ["fr"]


def test_pipeline_audio_selection_caps_articles_for_radio_flow(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "12")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss", priority=100))
    for index in range(12):
        pipeline.db.upsert_article(
            ArticleInput(
                source_name="Fixture",
                title=f"Information locale importante {index}",
                url=f"https://example.test/{index}",
                published_at=f"2026-05-17T12:{index:02d}:00+02:00",
                summary="Le canton presente une decision avec des effets concrets.",
                content="",
            )
        )

    selected = pipeline._select_articles("suisse_romande")

    assert len(selected) == 9


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


def test_draft_quality_issue_rejects_repeated_paragraph_openings():
    paragraph = "D'abord, le canton annonce une decision importante pour les habitants et les communes concernees."
    draft = BulletinDraft(
        title="Repetition",
        summary="",
        transcript="\n\n".join([paragraph] * 4) + " " + " ".join(["mot"] * 900),
    )
    assert _draft_quality_issue(draft) == "LLM returned repetitive paragraph openings: d'abord le canton"
