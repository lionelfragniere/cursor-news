from pathlib import Path
from dataclasses import replace

import pytest

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


def test_article_language_is_stored_per_article(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite3")
    db.init()
    db.upsert_source(FeedSource(name="Valais", url="https://example.test/rss", region="valais"))
    article_id, _ = db.upsert_article(
        ArticleInput(
            source_name="Valais",
            title="Der Staatsrat informiert über neue Massnahmen",
            url="https://example.test/de",
            published_at=None,
            summary="Die Regierung im Wallis stellt eine neue Regelung für die Gemeinden vor.",
            content="",
            language="de",
        )
    )

    archive = db.article_archive(limit=10)

    assert article_id is not None
    assert archive[0]["language"] == "de"


@pytest.mark.parametrize("date", ["2026-12-07T10:09:18+01:00", "2026-12-07T09:09:18Z", "2026-12-07T09:09:18"])
def test_future_dates_are_clamped_once_and_past_dates_preserved(tmp_path, monkeypatch, date):
    monkeypatch.setattr("cursor_news.database.utc_now", lambda: "2026-09-17T08:00:00+00:00")
    db = Database(tmp_path / "db.sqlite3")
    db.init()
    db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss"))
    article = ArticleInput("Fixture", "Public information", "https://example.test/news", date, "Details", "")
    db.upsert_article(article)
    assert db.article_archive()[0]["published_at"] == "2026-09-17T08:00:00+00:00"
    monkeypatch.setattr("cursor_news.database.utc_now", lambda: "2026-09-18T08:00:00+00:00")
    db.upsert_article(article)
    assert db.article_archive()[0]["published_at"] == "2026-09-17T08:00:00+00:00"
    # A valid publisher correction replaces the fallback date.
    corrected = replace(article, published_at="2026-09-16T10:00:00+02:00")
    db.upsert_article(corrected)
    assert db.article_archive()[0]["published_at"] == corrected.published_at
    db.upsert_article(article)
    assert db.article_archive()[0]["published_at"] == corrected.published_at


def test_exclusion_survives_reingestion_and_keeps_bulletin_history(tmp_path):
    db = Database(tmp_path / "db.sqlite3")
    db.init()
    db.upsert_source(FeedSource(name="Fixture", url="https://example.test/rss"))
    article = ArticleInput("Fixture", "Reference guide", "https://example.test/guide", None, "Details", "")
    article_id, _ = db.upsert_article(article)
    selected = db.list_candidate_articles(10)
    assert db.exclude_article(article.url)
    # A bulletin already generating when exclusion happens must not undo it.
    db.create_bulletin("history", "2026-09-17T08:00:00+00:00", StyleSlot("test", "Test", ""),
                       BulletinDraft("Test", "", "Test"), selected)
    assert db.upsert_article(article) == (article_id, False)
    assert db.upsert_article(article, archive_only=True) == (article_id, False)
    db.init()
    assert db.list_candidate_articles(10, include_english=True) == []
    assert db.list_recent_articles(10, include_english=True) == []
    assert db.article_archive(include_sports=True) == []
    assert db.article_archive(include_sports=False) == []
    assert db.bulletin_by_id("history")["sources"][0]["url"] == article.url
    with db.connect() as con:
        assert con.execute("SELECT status FROM articles WHERE id=?", (article_id,)).fetchone()[0] == "excluded"
