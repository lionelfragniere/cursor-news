from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import FeedSource


def load_sources(path: Path) -> list[FeedSource]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults: dict[str, Any] = data.get("defaults", {})
    sources: list[FeedSource] = []
    for item in data.get("sources", []):
        merged = {**defaults, **item}
        sources.append(
            FeedSource(
                name=str(merged["name"]),
                url=str(merged["url"]),
                region=str(merged.get("region", "general")),
                priority=int(merged.get("priority", 50)),
                interval_minutes=int(merged.get("interval_minutes", 5)),
                max_entries=int(merged.get("max_entries", 20)),
                enabled=bool(merged.get("enabled", True)),
            )
        )
    return sources
