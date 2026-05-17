from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str
    region: str = "general"
    priority: int = 50
    interval_minutes: int = 5
    max_entries: int = 20
    enabled: bool = True


@dataclass(frozen=True)
class ArticleInput:
    source_name: str
    title: str
    url: str
    published_at: str | None
    summary: str
    content: str


@dataclass(frozen=True)
class Article:
    id: int
    source_name: str
    title: str
    url: str
    published_at: str | None
    summary: str
    content: str
    priority: int = 50

    def prompt_text(self) -> str:
        body = self.content or self.summary
        body = " ".join(body.split())
        if len(body) > 1200:
            body = body[:1200].rsplit(" ", 1)[0] + "..."
        return f"- Source: {self.source_name}\n  Titre: {self.title}\n  URL: {self.url}\n  Date: {self.published_at or 'inconnue'}\n  Contenu: {body}"


@dataclass(frozen=True)
class StyleSlot:
    key: str
    label: str
    prompt: str


@dataclass(frozen=True)
class BulletinDraft:
    title: str
    summary: str
    transcript: str
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "BulletinDraft":
        return cls(
            title=str(value.get("title") or "Cursor News"),
            summary=str(value.get("summary") or ""),
            transcript=str(value.get("transcript") or ""),
            warnings=[str(item) for item in value.get("warnings", []) if item],
        )


@dataclass(frozen=True)
class AudioResult:
    path: Path
    mime_type: str
    duration_seconds: float | None
