from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .article_filter import anxiety_score, calm_score, is_child_unsuitable_article, story_key
from .database import Database
from .models import Article
from .settings import Settings


def export_site_news(
    settings: Settings,
    output_path: Path,
    limit: int = 400,
    include_sports: bool = False,
    include_english: bool = False,
) -> dict:
    db = Database(settings.database_path)
    db.init()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    articles = _export_articles(
        db,
        limit=max(1, limit),
        include_sports=include_sports,
        include_english=include_english,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(articles),
        "regions": sorted({item["region"] for item in articles if item["region"]}),
        "sources": sorted({item["source_name"] for item in articles if item["source_name"]}),
        "articles": articles,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _export_articles(db: Database, limit: int, include_sports: bool, include_english: bool) -> list[dict]:
    filters: list[str] = []
    if not include_sports:
        filters.append("a.is_sports = 0")
    if not include_english:
        filters.append("s.region != 'english'")
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with db.connect() as con:
        rows = con.execute(
            f"""
            SELECT a.id,
                   s.name AS source_name,
                   s.region,
                   s.priority,
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
                "search_terms": _search_terms(article, str(row["region"] or "general")),
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


def _search_terms(article: Article, region: str) -> str:
    if region != "english":
        return ""
    terms = ["english"]
    if article.source_name.startswith("UN News"):
        terms.extend(["UN", "ONU", "United Nations", "Nations Unies"])
    return " ".join(terms)
