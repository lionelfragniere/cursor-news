from __future__ import annotations

import re
from html import unescape
from urllib.parse import urldefrag

from bs4 import BeautifulSoup


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    text = soup.get_text(" ", strip=True)
    return normalize_text(unescape(text))


def normalize_text(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value


def canonicalize_url(url: str) -> str:
    clean, _fragment = urldefrag(url.strip())
    return clean


def extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    candidates = soup.find_all(["article", "main"])
    if candidates:
        text = " ".join(candidate.get_text(" ", strip=True) for candidate in candidates)
    else:
        text = soup.get_text(" ", strip=True)
    return normalize_text(text)
