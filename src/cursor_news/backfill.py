"""Recover dated public article metadata without adding old stories to the radio."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import json
import re
import shutil
import sqlite3
import subprocess
import time as clock
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urljoin, urlsplit
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import httpx
import yaml

from .database import Database
from .language import detect_article_language
from .models import ArticleInput, FeedSource
from .settings import load_settings
from .sources import load_sources
from .text import canonicalize_url, strip_html

ZONE = ZoneInfo("Europe/Zurich")
USER_AGENT = "CursorNews/0.1 public archive recovery"


def article_key(url: str) -> str:
    """Match the publishers' archive and RSS aliases without rewriting live rows."""
    parts = urlsplit(url)
    host, path = (parts.hostname or "").lower(), unquote(parts.path).rstrip("/")
    if host in {"www.bbc.co.uk", "www.bbc.com"}:
        host = "www.bbc.com"
    if host == "www.letemps.ch":
        path = "/articles/" + path.rsplit("/", 1)[-1]
    if host == "news.un.org":
        path = path.removeprefix("/feed/view")
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query)
                             if not k.lower().startswith(("utm_", "at_")) and k.lower() not in {"fbclid", "gclid"}))
    return host + path + ("?" + query if query else "")


def parse_date(value: str | None) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZONE)
    except ValueError:
        return None


def url_date(url: str) -> date | None:
    match = re.search(r"/(20\d{2})/?(\d{2})/?(\d{2})(?:[-/]|$)", unquote(urlsplit(url).path))
    try:
        return date(*map(int, match.groups())) if match else None
    except ValueError:
        return None


def article_metadata(html: str, url: str, source: FeedSource) -> ArticleInput | None:
    soup = BeautifulSoup(html, "html.parser")
    meta = {tag.get("property") or tag.get("name"): tag.get("content", "") for tag in soup.find_all("meta")}
    structured = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            nodes = json.loads(script.string or "{}")
        except (ValueError, TypeError):
            continue
        nodes = nodes if isinstance(nodes, list) else [nodes]
        for node in nodes:
            if isinstance(node, dict):
                structured.extend(node.get("@graph", [node]))
    article = next((node for node in structured if isinstance(node, dict) and any(
        kind in str(node.get("@type", "")) for kind in ("Article", "LiveBlogPosting", "Report")
    )), {})
    publication_tag = soup.select_one('[itemprop="datePublished"]')
    published = parse_date(meta.get("article:published_time") or meta.get("og:article:published_time")
                           or article.get("datePublished") or meta.get("datePublished")
                           or (publication_tag.get("datetime") or publication_tag.get("content")
                               if publication_tag else None))
    title = article.get("headline") or meta.get("og:title")
    description = meta.get("og:description") or meta.get("description") or article.get("description") or ""
    if not published or not isinstance(title, str) or not title.strip():
        return None
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and canonical.get("href"):
        candidate = urljoin(url, canonical["href"])
        if urlsplit(candidate).hostname == urlsplit(url).hostname:
            url = candidate
    if urlsplit(url).hostname in {"www.rtn.ch", "www.rjb.ch", "www.rfj.ch"}:
        login = soup.select_one('form[action*="ReturnURL="]')
        if login:
            return_url = parse_qs(urlsplit(login["action"]).query).get("ReturnURL", [""])[0]
            if re.fullmatch(r"/Scripts/Index\.aspx\?id=\d+", return_url):
                url = urljoin(url, return_url)
    title, description = strip_html(title), strip_html(str(description))
    return ArticleInput(source.name, title, canonicalize_url(url), published.isoformat(timespec="seconds"),
                        description, description, detect_article_language(title, description, description,
                                                                          source_region=source.region))


class ArchiveReader:
    def __init__(self, source: FeedSource, spec: dict, start: date, end: date, known: set[str]):
        self.source, self.spec = source, spec
        self.start, self.end, self.known = start, end, known
        self.client = httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        self.report = {"source": source.name, "discovered": 0, "existing": 0, "inserted": 0,
                       "outside_range": 0, "missing_metadata": 0, "errors": [], "inserted_ids": []}
        self.visited: set[str] = set()

    def fetch(self, url: str) -> str:
        clock.sleep(0.25)
        try:
            response = self.client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.TransportError:
            # Some regional radio sites need curl's TLS implementation.
            curl = shutil.which("curl.exe") or shutil.which("curl")
            if not curl:
                raise
            result = subprocess.run([curl, "-fsSL", "--max-time", "20", "-A", USER_AGENT, url],
                                    capture_output=True, check=True, timeout=25)
            return result.stdout.decode("utf-8")

    def urls(self):
        spec = self.spec
        if spec["kind"] == "radio":
            yield from self.radio_urls()
            return
        roots = list(dict.fromkeys(day.strftime(template.replace("%b", day.strftime("%b").lower())) for day in days(self.start, self.end)
                                  for template in spec["urls"]))
        queue = list(roots)
        visited: set[str] = set()
        while queue:
            url = canonicalize_url(queue.pop(0))
            if url in visited:
                continue
            if len(visited) >= 80:
                self.report["errors"].append("Archive index page limit reached")
                break
            visited.add(url)
            try:
                text = self.fetch(url)
                if spec["kind"] == "sitemap":
                    root = ET.fromstring(text)
                    if root.tag.endswith("sitemapindex"):
                        for node in root:
                            modified = parse_date(node.findtext("{*}lastmod"))
                            if node.findtext("{*}loc") and (not modified or modified.astimezone(ZONE).date() >= self.start):
                                queue.append(node.findtext("{*}loc"))
                    else:
                        for node in root.findall("{*}url"):
                            loc = node.findtext("{*}loc")
                            modified = parse_date(node.findtext("{*}lastmod"))
                            published = parse_date(node.findtext("{*}news/{*}publication_date"))
                            if published and not self.start <= published.astimezone(ZONE).date() < self.end:
                                continue
                            if loc and (not modified or modified.astimezone(ZONE).date() >= self.start):
                                yield loc
                else:
                    soup = BeautifulSoup(text, "html.parser")
                    for link in soup.select(spec.get("selector", "a[href]")):
                        if link.get("href"):
                            yield urljoin(url, link["href"])
                    if spec.get("pagination"):
                        prefix = roots[0]
                        queue.extend(urljoin(url, a["href"]) for a in soup.select("a[href]")
                                     if urljoin(url, a["href"]).startswith(prefix))
            except Exception as exc:
                self.report["errors"].append(f"Index {url}: {exc}")

    def radio_urls(self):
        base = self.spec["base"]
        robots = self.fetch(base + "/robots.txt")
        maps = re.findall(r"(?im)^sitemap:\s*(\S+)", robots)
        maps = [url for url in maps if re.search(r"_p\d+\.xml$", url)]
        maps.sort(key=lambda url: int(re.search(r"_p(\d+)\.xml$", url)[1]))
        target = (base + self.spec["article_path"] + self.start.strftime("%Y%m%d")).casefold()
        end_target = (base + self.spec["article_path"] + self.end.strftime("%Y%m%d")).casefold()
        cache = {}

        def entries(index):
            if index not in cache:
                root = ET.fromstring(self.fetch(maps[index]))
                cache[index] = [node.text for node in root.findall("{*}url/{*}loc") if node.text]
            return cache[index]

        # These published maps are sorted by URL, including dated regional articles.
        low, high = 0, len(maps)
        while low < high:
            middle = (low + high) // 2
            values = entries(middle)
            if values and values[-1].casefold() < target:
                low = middle + 1
            else:
                high = middle
        for index in range(low, min(low + 5, len(maps))):
            values = entries(index)
            if values and values[0].casefold() >= end_target:
                break
            yield from values

    def wordpress_articles(self):
        page = 1
        while page <= 30:
            url = self.spec["url"]
            params = {"after": f"{self.start}T00:00:00", "before": f"{self.end}T00:00:00",
                      "per_page": 100, "page": page, "_fields": "link,date_gmt,title,excerpt"}
            response = json.loads(self.fetch(str(httpx.URL(url, params=params))))
            if not isinstance(response, list):
                raise ValueError("Expected public WordPress posts")
            for post in response:
                title = strip_html(post["title"]["rendered"])
                summary = strip_html(post["excerpt"]["rendered"])
                yield ArticleInput(self.source.name, title, canonicalize_url(post["link"]),
                                   post["date_gmt"] + "+00:00", summary, summary,
                                   detect_article_language(title, summary, summary, source_region=self.source.region))
            if len(response) < 100:
                break
            page += 1

    def articles(self):
        if self.spec["kind"] == "wordpress":
            yield from self.wordpress_articles()
            return
        for raw_url in self.urls():
            url = canonicalize_url(raw_url)
            host = urlsplit(url).hostname or ""
            if host not in self.spec["hosts"] or not re.search(self.spec["article_pattern"], unquote(urlsplit(url).path)):
                continue
            day = url_date(url)
            if day and not self.start <= day < self.end:
                continue
            if url in self.visited:
                continue
            self.visited.add(url)
            self.report["discovered"] += 1
            if article_key(url) in self.known:
                self.report["existing"] += 1
                continue
            if len(self.visited) > 3000:
                self.report["errors"].append("Article limit reached")
                break
            try:
                article = article_metadata(self.fetch(url), url, self.source)
                if article:
                    yield article
                else:
                    self.report["missing_metadata"] += 1
            except Exception as exc:
                self.report["errors"].append(f"Article {url}: {exc}")

    def recover(self, db: Database) -> dict:
        try:
            for article in self.articles():
                published = parse_date(article.published_at)
                if not published or not self.start <= published.astimezone(ZONE).date() < self.end:
                    self.report["outside_range"] += 1
                    continue
                if article_key(article.url) in self.known:
                    self.report["existing"] += 1
                    continue
                article_id, created = db.upsert_article(article, archive_only=True)
                self.known.add(article_key(article.url))
                if created:
                    self.report["inserted"] += 1
                    self.report["inserted_ids"].append(article_id)
                    if self.report["inserted"] % 50 == 0:
                        print(f"{self.source.name}: {self.report['inserted']} recovered", flush=True)
                else:
                    self.report["existing"] += 1
        except Exception as exc:
            self.report["errors"].append(str(exc))
        finally:
            self.client.close()
        if self.spec["kind"] != "wordpress" and self.report["discovered"] == 0:
            self.report["errors"].append("No indexed article discovered; coverage could not be confirmed")
        return self.report


def days(start: date, end: date):
    while start < end:
        yield start
        start += timedelta(days=1)


def audit(db: Database, start: date, end: date) -> dict:
    counts = {str(day): {"published": 0, "collected": 0} for day in days(start, end)}
    with db.connect() as con:
        rows = con.execute("SELECT published_at, created_at FROM articles WHERE published_at >= ? OR created_at >= ?",
                           (str(start - timedelta(days=1)), str(start - timedelta(days=1)))).fetchall()
    for row in rows:
        for column, label in (("published_at", "published"), ("created_at", "collected")):
            parsed = parse_date(row[column])
            day = str(parsed.astimezone(ZONE).date()) if parsed else ""
            if day in counts:
                counts[day][label] += 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="Exclusive end date, Europe/Zurich")
    parser.add_argument("--source", action="append", default=[], help="Source name substring; repeatable")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    if not args.start < args.end or (args.end - args.start).days > 31:
        parser.error("Choose a date range of 1 to 31 days")
    settings = load_settings()
    db = Database(settings.database_path)
    before = audit(db, args.start, args.end)
    if args.audit_only:
        print(json.dumps(before, indent=2))
        return
    sources = {s.name: s for s in load_sources(settings.sources_path) if s.enabled}
    specs = yaml.safe_load((settings.home / "config/backfill.yml").read_text(encoding="utf-8"))["archives"]
    unsupported = sorted(set(sources) - {spec["source"] for spec in specs})
    specs = [spec for spec in specs if spec["source"] in sources and
             (not args.source or any(term.casefold() in spec["source"].casefold() for term in args.source))]
    if not specs:
        parser.error("No configured archive matches the selected sources")
    output = settings.data_dir / "backfill" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    output.mkdir(parents=True)
    with closing(sqlite3.connect(settings.database_path)) as live, closing(sqlite3.connect(output / "before.sqlite3")) as backup:
        live.backup(backup)
    with db.connect() as con:
        known = {article_key(row["url"]) for row in con.execute("SELECT url FROM articles")}
    report = {"start": str(args.start), "end_exclusive": str(args.end), "before": before, "sources": [],
              "unsupported_sources": unsupported}
    report_path = output / "report.json"
    print(f"Backup and report: {output}", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = [pool.submit(ArchiveReader(sources[spec["source"]], spec, args.start, args.end, known).recover, db)
                for spec in specs]
        for job in as_completed(jobs):
            result = job.result()
            report["sources"].append(result)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Finished {result['source']}: {result['inserted']} inserted, {len(result['errors'])} errors", flush=True)
    report["after"] = audit(db, args.start, args.end)
    report["inserted"] = sum(r["inserted"] for r in report["sources"])
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"inserted": report["inserted"], "report": str(report_path)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
