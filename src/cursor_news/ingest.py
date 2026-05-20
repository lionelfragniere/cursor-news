from __future__ import annotations

from dataclasses import replace
import shutil
import subprocess
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import mktime
from typing import Any

import feedparser
import httpx

from .database import Database
from .language import detect_article_language
from .models import ArticleInput, FeedSource
from .sources import load_sources
from .text import canonicalize_url, extract_main_text, normalize_text, strip_html


class FeedIngestor:
    def __init__(self, db: Database, sources_path, timeout_seconds: float = 15.0):
        self.db = db
        self.sources_path = sources_path
        self.timeout_seconds = timeout_seconds

    def ingest_all(self) -> dict[str, Any]:
        self.db.init()
        sources = [source for source in load_sources(self.sources_path) if source.enabled]
        results = []
        total_new = 0
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            for source in sources:
                self.db.upsert_source(source)
                result = self._ingest_source(client, source)
                total_new += result["new_articles"]
                results.append(result)
        return {"sources": results, "new_articles": total_new}

    def _ingest_source(self, client: httpx.Client, source: FeedSource) -> dict[str, Any]:
        cache = self.db.source_cache(source.name)
        headers = {
            "User-Agent": "CursorNews/0.1 RSS prototype",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        }
        if cache.get("last_etag"):
            headers["If-None-Match"] = str(cache["last_etag"])
        if cache.get("last_modified"):
            headers["If-Modified-Since"] = str(cache["last_modified"])

        response, content = self._fetch_feed(client, source.url, headers)
        if response is not None and response.status_code == 304:
            self.db.update_source_fetch_state(source.name, None, None)
            return {"source": source.name, "status": "not_modified", "new_articles": 0}
        response_headers = response.headers if response is not None else {}

        parsed = feedparser.parse(content)
        new_articles = 0
        entries = parsed.entries if source.max_entries <= 0 else parsed.entries[: source.max_entries]
        for entry in entries:
            article = self._entry_to_article(source, entry)
            if not article:
                continue
            if source.region != "english" and len(article.content) < 260 and article.url:
                article = self._enrich_article(client, article)
            article = self._with_detected_language(source, article)
            _article_id, created = self.db.upsert_article(article)
            if created:
                new_articles += 1

        self.db.update_source_fetch_state(
            source.name,
            response_headers.get("etag"),
            response_headers.get("last-modified"),
        )
        return {"source": source.name, "status": "ok", "new_articles": new_articles, "entries": len(entries), "available": len(parsed.entries)}

    def _fetch_feed(self, client: httpx.Client, url: str, headers: dict[str, str]) -> tuple[httpx.Response | None, bytes]:
        try:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response, response.content
        except httpx.HTTPError:
            curl_path = shutil.which("curl.exe") or shutil.which("curl")
            if not curl_path:
                raise
            command = [
                curl_path,
                "-L",
                "--max-time",
                str(int(self.timeout_seconds)),
                "-sS",
                "-A",
                headers["User-Agent"],
                "-H",
                f"Accept: {headers['Accept']}",
                url,
            ]
            result = subprocess.run(command, check=False, capture_output=True)
            if result.returncode != 0 or not result.stdout:
                raise
            return None, result.stdout

    def _entry_to_article(self, source: FeedSource, entry: Any) -> ArticleInput | None:
        title = normalize_text(getattr(entry, "title", ""))
        link = canonicalize_url(getattr(entry, "link", ""))
        if not title or not link:
            return None

        summary = strip_html(getattr(entry, "summary", ""))
        content = ""
        if getattr(entry, "content", None):
            content = " ".join(strip_html(item.get("value", "")) for item in entry.content)
        if not content:
            content = summary

        return ArticleInput(
            source_name=source.name,
            title=title,
            url=link,
            published_at=_entry_date(entry),
            summary=summary,
            content=normalize_text(content),
            language=detect_article_language(title, summary, content, source_region=source.region),
        )

    def _enrich_article(self, client: httpx.Client, article: ArticleInput) -> ArticleInput:
        try:
            response = client.get(
                article.url,
                headers={"User-Agent": "CursorNews/0.1 article fetch", "Accept": "text/html, */*"},
            )
            response.raise_for_status()
            text = extract_main_text(response.text)
            if len(text) > len(article.content):
                return ArticleInput(
                    source_name=article.source_name,
                    title=article.title,
                    url=article.url,
                    published_at=article.published_at,
                    summary=article.summary,
                    content=text[:4000],
                    language=article.language,
                )
        except Exception:
            return article
        return article

    def _with_detected_language(self, source: FeedSource, article: ArticleInput) -> ArticleInput:
        language = detect_article_language(
            article.title,
            article.summary,
            article.content,
            source_region=source.region,
        )
        return replace(article, language=language)


def _entry_date(entry: Any) -> str | None:
    for attr in ("published_parsed", "updated_parsed"):
        value = getattr(entry, attr, None)
        if value:
            return datetime.fromtimestamp(mktime(value), tz=timezone.utc).isoformat(timespec="seconds")
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat(timespec="seconds")
            except Exception:
                return str(raw)
    return None
