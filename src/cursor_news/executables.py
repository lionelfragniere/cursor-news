from __future__ import annotations

import shutil
from pathlib import Path


def resolve_executable(configured_path: str | None, fallback_name: str) -> str | None:
    if not configured_path:
        return shutil.which(fallback_name)

    value = configured_path.strip()
    if not value:
        return shutil.which(fallback_name)

    path = Path(value)
    if path.exists():
        return str(path)

    normalized_value = value.replace("\\", "/")
    if normalized_value != value:
        normalized_path = Path(normalized_value)
        if normalized_path.exists():
            return str(normalized_path)

    return shutil.which(fallback_name)
