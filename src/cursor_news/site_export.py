from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .article_filter import anxiety_score, calm_score, is_child_unsuitable_article, rank_articles_for_topic, story_key, topic_relevance_score
from .database import Database
from .models import Article, StyleSlot
from .schedule import ProgramSchedule
from .settings import Settings


def export_site_news(
    settings: Settings,
    output_path: Path,
    limit: int = 400,
    include_sports: bool = False,
    include_english: bool = False,
    include_german: bool = False,
) -> dict:
    db = Database(settings.database_path)
    db.init()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    articles = _export_articles(
        db,
        limit=max(1, limit),
        include_sports=include_sports,
        include_english=include_english,
        include_german=include_german,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(articles),
        "regions": sorted({item["region"] for item in articles if item["region"]}),
        "languages": sorted({item["language"] for item in articles if item["language"]}),
        "sources": sorted({item["source_name"] for item in articles if item["source_name"]}),
        "articles": articles,
        "topic_summaries": build_topic_summaries(articles, ProgramSchedule.load(settings.schedule_path).rotation)
        if settings.schedule_path.exists() else [],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def build_topic_summaries(items: list[dict], topics: list[StyleSlot], now: datetime | None = None) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(hours=24)
    articles = []
    by_id = {}
    for item in items:
        try:
            published = datetime.fromisoformat((item.get("published_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if not cutoff <= published <= current or item.get("is_sports"):
            continue
        article = Article(
            id=item["id"], source_name=item["source_name"], title=item["title"], url=item["url"],
            published_at=item["published_at"], summary=item.get("summary", ""), content="",
            region=item["region"], language=item.get("language", "unknown"), priority=item.get("priority", 50),
        )
        articles.append(article)
        by_id[article.id] = item
    summaries = []
    for topic in topics:
        focused = [a for a in articles if a.language == topic.language and topic_relevance_score(a, topic.key) > 0]
        selected = rank_articles_for_topic(focused, topic.key)[:3]
        if selected:
            summaries.append({
                "topic_key": topic.key, "label": topic.label, "language": topic.language,
                "articles": [{key: by_id[a.id].get(key) for key in
                              ("id", "title", "summary", "url", "source_name", "published_at")} for a in selected],
            })
    return summaries


def _export_articles(
    db: Database,
    limit: int,
    include_sports: bool,
    include_english: bool,
    include_german: bool,
) -> list[dict]:
    filters: list[str] = ["a.status != 'excluded'"]
    if not include_sports:
        filters.append("a.is_sports = 0")
    if not include_english:
        filters.append("s.region != 'english'")
        filters.append("a.language != 'en'")
    if not include_german:
        filters.append("a.language != 'de'")
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with db.connect() as con:
        rows = con.execute(
            f"""
            SELECT a.id,
                   s.name AS source_name,
                   s.region,
                   s.priority,
                   a.language,
                   a.title,
                   a.url,
                   a.published_at,
                   a.scraped_at,
                   a.summary,
                   a.content,
                   a.status,
                   a.is_sports,
                   a.used_count
            FROM articles a
            JOIN sources s ON s.id = a.source_id
            {where}
            ORDER BY COALESCE(a.published_at, a.created_at) DESC, s.priority DESC
            LIMIT ?
            """,
            (limit * 3,),
        ).fetchall()

    items: list[dict] = []
    seen_stories: set[str] = set()
    for row in rows:
        article = Article(
            id=int(row["id"]),
            source_name=str(row["source_name"]),
            title=str(row["title"]),
            url=str(row["url"]),
            published_at=row["published_at"],
            summary=str(row["summary"] or ""),
            content=str(row["content"] or ""),
            priority=int(row["priority"]),
            region=str(row["region"] or "general"),
            language=str(row["language"] or "unknown"),
        )
        key = story_key(article)
        if key in seen_stories:
            continue
        seen_stories.add(key)
        tension = min(10, anxiety_score(article))
        calm = min(10, calm_score(article))
        child_unsuitable = is_child_unsuitable_article(article)
        excerpt = _excerpt(article.summary or article.content)
        items.append(
            {
                "id": article.id,
                "source_name": article.source_name,
                "region": str(row["region"] or "general"),
                "language": article.language,
                "priority": article.priority,
                "title": article.title,
                "url": article.url,
                "published_at": article.published_at,
                "scraped_at": row["scraped_at"],
                "summary": excerpt,
                "status": str(row["status"]),
                "is_sports": bool(row["is_sports"]),
                "used_count": int(row["used_count"]),
                "tension": tension,
                "calm": calm,
                "child_friendly": not child_unsuitable and not bool(row["is_sports"]),
                "search_terms": _search_terms(article, str(row["region"] or "general"), article.language),
            }
        )
        if len(items) >= limit:
            break
    return items


def _excerpt(text: str, max_length: int = 320) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= max_length:
        return clean
    return clean[:max_length].rsplit(" ", 1)[0] + "..."


def _search_terms(article: Article, region: str, language: str) -> str:
    if language == "de":
        return "de deutsch allemand valais oberwallis haut-valais"
    if region != "english":
        return ""
    terms = ["english"]
    if article.source_name.startswith("UN News"):
        terms.extend(["UN", "ONU", "United Nations", "Nations Unies"])
    return " ".join(terms)
