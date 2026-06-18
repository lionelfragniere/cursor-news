from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

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
    pipeline.db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss", region="suisse-romande"))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Une nouvelle liaison ferroviaire est annoncée",
            url="https://example.test/train",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Le canton présente une mesure de mobilité publique.",
            content="",
        )
    )
    generated = pipeline.generate_buffer(now=datetime(2026, 1, 1, 0, 0, tzinfo=ZoneInfo("Europe/Zurich")))
    assert generated
    current = pipeline.db.current_bulletin()
    assert current is not None
    assert Path(current["audio_path"]).exists()


def test_pipeline_skips_empty_slots_without_fallback_audio(tmp_path: Path, monkeypatch):
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

    generated = pipeline.generate_buffer(now=datetime(2026, 1, 1, 0, 0, tzinfo=ZoneInfo("Europe/Zurich")))

    assert generated == []
    assert pipeline.db.current_bulletin() is None


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


def test_pipeline_un_bulletin_does_not_backfill_unrelated_english_news(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "5")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="UN News", url="https://news.un.org/rss", region="english", priority=100))
    pipeline.db.upsert_source(FeedSource(name="BBC News - World", url="https://bbc.com/rss", region="english", priority=150))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="UN News",
            title="UN agencies call for humanitarian access",
            url="https://news.un.org/en/story",
            published_at="2026-05-17T12:10:00+02:00",
            summary="UN agencies call for better access to civilians.",
            content="",
            language="en",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="BBC News - World",
            title="Australia announces a tax measure",
            url="https://bbc.com/story",
            published_at="2026-05-17T12:00:00+02:00",
            summary="The government outlines a domestic tax plan.",
            content="",
            language="en",
        )
    )

    selected = pipeline._select_articles("un_relevant")

    assert selected
    assert [article.source_name for article in selected] == ["UN News"]


def test_pipeline_un_bulletin_returns_empty_without_official_un_news(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "5")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="The Guardian - World", url="https://guardian.test/rss", region="english", priority=150))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="The Guardian - World",
            title="Middle East humanitarian talks continue",
            url="https://guardian.test/story",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Diplomats discuss humanitarian access and human rights.",
            content="",
            language="en",
        )
    )

    selected = pipeline._select_articles("un_relevant")

    assert selected == []


def test_pipeline_un_bulletin_searches_deep_enough_for_official_un_news(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "5")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="BBC News - World", url="https://bbc.test/rss", region="english", priority=150))
    pipeline.db.upsert_source(FeedSource(name="UN News - Humanitarian Aid", url="https://news.un.org/rss", region="english", priority=100))
    for index in range(140):
        pipeline.db.upsert_article(
            ArticleInput(
                source_name="BBC News - World",
                title=f"World update {index}",
                url=f"https://bbc.test/{index}",
                published_at=f"2026-05-17T14:{index % 60:02d}:00+02:00",
                summary="A global political update is reported.",
                content="",
                language="en",
            )
        )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="UN News - Humanitarian Aid",
            title="UN agencies warn humanitarian access is under pressure",
            url="https://news.un.org/en/humanitarian-access",
            published_at="2026-05-17T12:00:00+02:00",
            summary="UN agencies say humanitarian teams need safer access to civilians.",
            content="",
            language="en",
        )
    )

    selected = pipeline._select_articles("un_relevant")

    assert selected
    assert {article.source_name for article in selected} == {"UN News - Humanitarian Aid"}


def test_pipeline_un_bulletin_prefers_official_un_news(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "5")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="UN News - Humanitarian Aid", url="https://news.un.org/rss", region="english", priority=100))
    pipeline.db.upsert_source(FeedSource(name="The Guardian - World", url="https://guardian.test/rss", region="english", priority=150))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="UN News - Humanitarian Aid",
            title="UN agencies call for humanitarian access",
            url="https://news.un.org/en/story",
            published_at="2026-05-17T12:10:00+02:00",
            summary="UN agencies call for better access to civilians.",
            content="",
            language="en",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="The Guardian - World",
            title="Middle East humanitarian talks continue",
            url="https://guardian.test/story",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Diplomats discuss humanitarian access.",
            content="",
            language="en",
        )
    )

    selected = pipeline._select_articles("un_relevant")

    assert selected
    assert {article.source_name for article in selected} == {"UN News - Humanitarian Aid"}


def test_pipeline_english_selection_skips_world_cup_sports_item(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "5")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="BBC News - World", url="https://bbc.com/rss", region="english", priority=150))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="BBC News - World",
            title="From one to 48 - every World Cup team ranked after first game",
            url="https://bbc.com/sport",
            published_at="2026-05-17T12:10:00+02:00",
            summary="All 48 teams at the World Cup have now played once.",
            content="",
            language="en",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="BBC News - World",
            title="UN warns of worsening humanitarian access",
            url="https://bbc.com/news",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Humanitarian agencies say access is getting harder.",
            content="",
            language="en",
        )
    )

    selected = pipeline._select_articles("international_english")

    assert [article.title for article in selected] == ["UN warns of worsening humanitarian access"]


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


def test_pipeline_french_bulletin_excludes_unknown_german_articles(tmp_path: Path, monkeypatch):
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
            title="Die Woche im Oberwallis",
            url="https://example.test/de-unknown",
            published_at="2026-05-17T12:10:00+02:00",
            summary="Jeden Freitag präsentiert die Redaktion eine Auswahl der wichtigsten Themen aus dem Oberwallis.",
            content="",
            language="unknown",
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
    assert [article.title for article in selected] == ["Le Valais présente une nouvelle mesure"]


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

    assert len(selected) == 7


def test_pipeline_security_selection_does_not_backfill_unrelated_news(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "5")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="Canal9", url="https://canal9.test/rss", region="valais", priority=150))
    pipeline.db.upsert_source(FeedSource(name="RFI - Français", url="https://rfi.test/rss", region="international", priority=100))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Canal9",
            title="La protection de la vigne",
            url="https://canal9.test/vigne",
            published_at="2026-05-17T12:00:00+02:00",
            summary="Au printemps, la vigne est vulnérable aux ravageurs.",
            content="Liens de page: guerre, conflit, attaque.",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="RFI - Français",
            title="Cyberattaque contre une administration européenne",
            url="https://rfi.test/cyber",
            published_at="2026-05-17T12:10:00+02:00",
            summary="Les autorités enquêtent sur une attaque informatique visant des services publics.",
            content="",
        )
    )

    selected = pipeline._select_articles("security_world")

    assert [article.title for article in selected] == ["Cyberattaque contre une administration européenne"]


def test_draft_quality_issue_rejects_short_llm_output():
    draft = BulletinDraft(title="Court", summary="", transcript="Trop court.")
    assert _draft_quality_issue(draft) == "LLM returned a short transcript (2 words)"


def test_draft_quality_accepts_radio_length_valid_llm_output():
    draft = BulletinDraft(title="Format radio", summary="", transcript=" ".join(["mot"] * 650))
    assert _draft_quality_issue(draft) is None


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


def test_draft_quality_rejects_invented_romandy_impact_filler():
    draft = BulletinDraft(
        title="Impact invente",
        summary="",
        transcript=" ".join(["mot"] * 350) + " La Suisse romande, en tant que pays neutre, doit surveiller ce dossier.",
    )
    assert _draft_quality_issue(draft) == "LLM returned generic radio filler: pays neutre"


def test_pipeline_international_selection_does_not_backfill_local_news(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("CURSOR_NEWS_MAX_ARTICLES", "5")
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.db.upsert_source(FeedSource(name="Canal9", url="https://canal9.test/rss", region="valais", priority=150))
    pipeline.db.upsert_source(FeedSource(name="RFI - Francais", url="https://rfi.test/rss", region="international", priority=100))
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="Canal9",
            title="Un nouveau projet communal est presente a Sion",
            url="https://canal9.test/sion",
            published_at="2026-05-17T12:00:00+02:00",
            summary="La ville presente une mesure locale pour les quartiers.",
            content="",
        )
    )
    pipeline.db.upsert_article(
        ArticleInput(
            source_name="RFI - Francais",
            title="Europe: les dirigeants discutent d'un nouvel accord",
            url="https://rfi.test/europe",
            published_at="2026-05-17T12:10:00+02:00",
            summary="Une reunion internationale se tient avec plusieurs pays europeens.",
            content="",
        )
    )

    selected = pipeline._select_articles("international")

    assert [article.title for article in selected] == ["Europe: les dirigeants discutent d'un nouvel accord"]
