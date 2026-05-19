from pathlib import Path

from cursor_news.database import Database
from cursor_news.models import ArticleInput, BulletinDraft, FeedSource, StyleSlot


def test_article_deduplication(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.init()
    db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss"))
    article = ArticleInput(
        source_name="Fixture",
        title="Titre",
        url="https://example.test/a#fragment",
        published_at=None,
        summary="Resume",
        content="Contenu",
    )
    first_id, first_created = db.upsert_article(article)
    second_id, second_created = db.upsert_article(article)
    assert first_id == second_id
    assert first_created is True
    assert second_created is False
    assert len(db.list_candidate_articles(10)) == 1


def test_recent_articles_include_used_articles(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.init()
    db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss"))
    article_id, _ = db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Titre",
            url="https://example.test/a",
            published_at=None,
            summary="Résumé",
            content="Contenu",
        )
    )
    article = db.list_candidate_articles(10)[0]
    db.create_bulletin(
        bulletin_id="test-bulletin",
        slot_start="2026-05-17T12:00:00+02:00",
        style=StyleSlot(key="journaliste", label="Journaliste", prompt=""),
        draft=BulletinDraft(title="Test", summary="", transcript="Test"),
        articles=[article],
    )
    assert article_id is not None
    assert db.list_candidate_articles(10) == []
    assert [item.id for item in db.list_recent_articles(10)] == [article_id]


def test_database_classifies_sports_and_keeps_archive(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.init()
    db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss"))
    db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Football : un changement d'entraîneur annoncé",
            url="https://example.test/sport",
            published_at=None,
            summary="Le club change de coach.",
            content="",
        )
    )
    db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Une réforme de la santé est présentée",
            url="https://example.test/news",
            published_at=None,
            summary="Le gouvernement détaille son projet.",
            content="",
        )
    )
    assert [item.title for item in db.list_candidate_articles(10)] == ["Une réforme de la santé est présentée"]
    archive = db.article_archive(limit=10)
    assert len(archive) == 2
    assert sum(item["is_sports"] for item in archive) == 1
    status = db.status_snapshot()
    assert status["archive"]["total"] == 2
    assert status["archive"]["sports"] == 1
    assert status["archive"]["editorial"] == 1


def test_english_articles_are_excluded_from_bulletin_candidates(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.init()
    db.upsert_source(FeedSource(name="UN News", url="https://news.un.org/rss", region="english", priority=45))
    db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss", region="suisse-romande", priority=140))
    db.upsert_article(
        ArticleInput(
            source_name="UN News",
            title="Security Council discusses humanitarian access",
            url="https://news.un.org/en/story/1",
            published_at=None,
            summary="A United Nations meeting focuses on access for aid workers.",
            content="",
        )
    )
    local_id, _ = db.upsert_article(
        ArticleInput(
            source_name="Fixture",
            title="Une actualité locale reste candidate",
            url="https://example.test/local",
            published_at=None,
            summary="Un sujet romand de société.",
            content="",
        )
    )

    assert [item.id for item in db.list_candidate_articles(10)] == [local_id]
    assert [item.id for item in db.list_recent_articles(10)] == [local_id]
