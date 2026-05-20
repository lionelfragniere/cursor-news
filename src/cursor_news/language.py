from __future__ import annotations

import re
import unicodedata


KNOWN_LANGUAGES = {"fr", "en", "de", "unknown"}

_WORD_RE = re.compile(r"[a-zA-ZÀ-ÖØ-öø-ÿ0-9']+")

_FRENCH_WORDS = {
    "au",
    "aux",
    "avec",
    "ce",
    "ces",
    "cette",
    "dans",
    "de",
    "des",
    "du",
    "elle",
    "en",
    "est",
    "et",
    "le",
    "les",
    "leur",
    "lui",
    "mais",
    "par",
    "pas",
    "pour",
    "que",
    "qui",
    "se",
    "son",
    "sur",
    "une",
}

_ENGLISH_WORDS = {
    "a",
    "after",
    "and",
    "as",
    "at",
    "for",
    "from",
    "has",
    "in",
    "is",
    "its",
    "of",
    "on",
    "said",
    "the",
    "to",
    "united",
    "was",
    "with",
}

_GERMAN_WORDS = {
    "aber",
    "als",
    "am",
    "auch",
    "auf",
    "aus",
    "bei",
    "das",
    "dem",
    "den",
    "der",
    "des",
    "die",
    "eine",
    "einem",
    "einen",
    "einer",
    "für",
    "im",
    "ist",
    "mit",
    "nach",
    "nicht",
    "sich",
    "und",
    "von",
    "zum",
    "zur",
}


def normalize_article_language(value: str | None) -> str:
    language = (value or "").strip().lower()
    if language in {"fra", "fre", "fr-fr", "fr_ch", "fr-ch"}:
        return "fr"
    if language in {"eng", "en-us", "en-gb"}:
        return "en"
    if language in {"deu", "ger", "de-ch", "de-de"}:
        return "de"
    return language if language in KNOWN_LANGUAGES else "unknown"


def detect_article_language(
    title: str,
    summary: str = "",
    content: str = "",
    *,
    source_region: str = "",
) -> str:
    region = (source_region or "").strip().lower()
    if region == "english":
        return "en"

    text = " ".join(part for part in (title, summary, content[:1800]) if part).strip()
    if not text:
        return "unknown"

    words = [_strip_accents(word.lower()) for word in _WORD_RE.findall(text)]
    if len(words) < 4:
        return "unknown"

    raw_lower = text.lower()
    scores = {
        "fr": _score(words, _FRENCH_WORDS),
        "en": _score(words, _ENGLISH_WORDS),
        "de": _score(words, _GERMAN_WORDS),
    }
    scores["fr"] += _accent_bonus(raw_lower, "àâçéèêëîïôùûüÿœæ")
    scores["de"] += _accent_bonus(raw_lower, "äöüß")

    best_language, best_score = max(scores.items(), key=lambda item: item[1])
    second_score = max(score for language, score in scores.items() if language != best_language)
    if best_score < 4:
        return "unknown"
    if best_language == "de" and best_score >= second_score + 2:
        return "de"
    if best_language == "en" and best_score >= second_score + 2:
        return "en"
    if best_language == "fr" and best_score >= second_score:
        return "fr"
    return "unknown"


def _score(words: list[str], markers: set[str]) -> int:
    return sum(1 for word in words if word in markers)


def _accent_bonus(text: str, chars: str) -> int:
    return sum(2 for char in chars if char in text)


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")
