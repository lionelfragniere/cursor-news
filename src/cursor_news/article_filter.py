from __future__ import annotations

import re
import unicodedata

from .models import Article


SPORT_STRONG_PATTERNS = (
    r"\bfootball\b",
    r"\bfootballeur\b",
    r"\bfootballeuse\b",
    r"\bfoot\b",
    r"\bsportif\b",
    r"\bsportive\b",
    r"\bathlete\b",
    r"\bpremier league\b",
    r"\bligue\s*1\b",
    r"\bligue\s*2\b",
    r"\bchampions league\b",
    r"\bligue des champions\b",
    r"\bligue europa\b",
    r"\brugby\b",
    r"\btennis\b",
    r"\broland[- ]garros\b",
    r"\bwimbledon\b",
    r"\bnba\b",
    r"\bformule\s*1\b",
    r"\bf1\b",
    r"\bgrand prix\b",
    r"\bcyclisme\b",
    r"\btour de france\b",
    r"\bbasket\b",
    r"\bhandball\b",
    r"\bvolley\b",
    r"\bhockey\b",
    r"\bmercato\b",
)

SPORT_CONTEXT_PATTERNS = (
    r"\bentraineur\b",
    r"\bselectionneur\b",
    r"\bcoach\b",
    r"\bmatch\b",
    r"\bscore\b",
    r"\bbut\b",
    r"\bbuteur\b",
    r"\bvictoire\b",
    r"\bdefaite\b",
    r"\btransfert\b",
    r"\bjoueur\b",
    r"\bjoueuse\b",
    r"\bclub\b",
    r"\bstade\b",
)

SPORT_TEAM_PATTERNS = (
    r"\bchelsea\b",
    r"\breal madrid\b",
    r"\bpsg\b",
    r"\bolympique de marseille\b",
    r"\bom\b",
    r"\bolympique lyonnais\b",
    r"\bol\b",
    r"\bfc\b",
)

CHILD_UNSUITABLE_PATTERNS = (
    r"\bsexualite\b",
    r"\bsexuel\b",
    r"\bsexuels\b",
    r"\bsexuelle\b",
    r"\bsexuelles\b",
    r"\bsexe\b",
    r"\bviol\b",
    r"\bviols\b",
    r"\bporn",
    r"\bprostitution\b",
    r"\bsuicide\b",
    r"\bmeurtre\b",
    r"\bassassinat\b",
    r"\bcadavre\b",
    r"\bmorts?\b",
    r"\bmortes?\b",
    r"\best\s+morte?\b",
    r"\bmorte?\s+a\s+l.?age\b",
    r"\bdeces\b",
    r"\bdeced",
    r"\bdeuil\b",
    r"\bobseques\b",
    r"\bfunerailles\b",
    r"\btorture\b",
    r"\botage\b",
    r"\bpedocriminal",
    r"\bjihad",
    r"\bterroris",
    r"\bfauche",
    r"\bhumiliation\b",
    r"\bhumilie",
    r"\bcontrainte?\b",
    r"\brasee?\b",
    r"\bviolences?\b",
)

ANXIETY_STRONG_PATTERNS = (
    r"\bguerre\b",
    r"\bconflit\b",
    r"\battaque\b",
    r"\battentat\b",
    r"\bbombard",
    r"\bdrone",
    r"\bmort\b",
    r"\bmorts\b",
    r"\bbless",
    r"\bcrise\b",
    r"\bdeuil\b",
    r"\bobseques\b",
    r"\burgence\b",
    r"\balerte\b",
    r"\bepidemie\b",
    r"\bebola\b",
    r"\bvirus\b",
    r"\bmenace\b",
    r"\bjihad",
    r"\bterroris",
    r"\bsecurite\b",
    r"\barmee\b",
    r"\bpolice\b",
    r"\bmanifestants?\b",
    r"\baffrontements?\b",
    r"\bincendie\b",
    r"\binondation\b",
)

CALM_PATTERNS = (
    r"\bculture\b",
    r"\bfestival\b",
    r"\bcannes\b",
    r"\bmusique\b",
    r"\bfilm\b",
    r"\bcinema\b",
    r"\bscience\b",
    r"\brecherche\b",
    r"\bdecouverte\b",
    r"\beducation\b",
    r"\bpatrimoine\b",
    r"\bsolidarite\b",
    r"\bsolution\b",
    r"\bsoigner\b",
)


def is_sports_article(article: Article) -> bool:
    return is_sports_text(article.title, article.summary, article.content)


def is_sports_text(title: str, summary: str = "", content: str = "") -> bool:
    text = _normalize(" ".join([title, summary, content]))
    if _matches_any(text, SPORT_STRONG_PATTERNS):
        return True
    context_hits = sum(1 for pattern in SPORT_CONTEXT_PATTERNS if re.search(pattern, text))
    has_team = _matches_any(text, SPORT_TEAM_PATTERNS)
    return has_team and context_hits >= 1 or context_hits >= 3


def filter_sports_articles(articles: list[Article]) -> list[Article]:
    return [article for article in articles if not is_sports_article(article)]


def is_child_unsuitable_article(article: Article) -> bool:
    text = _normalize(" ".join([article.title, article.summary, article.content]))
    return _matches_any(text, CHILD_UNSUITABLE_PATTERNS)


def filter_child_unsuitable_articles(articles: list[Article]) -> list[Article]:
    return [article for article in articles if not is_child_unsuitable_article(article)]


def anxiety_score(article: Article) -> int:
    text = _normalize(" ".join([article.title, article.summary, article.content]))
    return sum(2 for pattern in ANXIETY_STRONG_PATTERNS if re.search(pattern, text))


def calm_score(article: Article) -> int:
    text = _normalize(" ".join([article.title, article.summary, article.content]))
    return sum(1 for pattern in CALM_PATTERNS if re.search(pattern, text))


def rank_articles_for_style(articles: list[Article], style_key: str | None) -> list[Article]:
    if style_key == "anxiogene":
        return [
            article
            for _index, article in sorted(
                enumerate(articles),
                key=lambda item: (-anxiety_score(item[1]), item[0]),
            )
        ]
    if style_key == "non_anxiogene":
        low_anxiety = [article for article in articles if anxiety_score(article) <= 1]
        high_anxiety = [article for article in articles if anxiety_score(article) > 1]
        low_anxiety = [
            article
            for _index, article in sorted(
                enumerate(low_anxiety),
                key=lambda item: (-calm_score(item[1]), item[0]),
            )
        ]
        if len(low_anxiety) >= 6:
            return low_anxiety
        return [*low_anxiety, *high_anxiety]
    return articles


def diversify_articles_by_topic(articles: list[Article]) -> list[Article]:
    unique: list[Article] = []
    duplicates: list[Article] = []
    seen: set[str] = set()
    for article in articles:
        key = topic_key(article)
        if key in seen:
            duplicates.append(article)
            continue
        seen.add(key)
        unique.append(article)
    return [*unique, *duplicates]


def unique_articles_by_topic(articles: list[Article]) -> list[Article]:
    unique: list[Article] = []
    seen: set[str] = set()
    for article in articles:
        key = topic_key(article)
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique


def unique_articles_by_story(articles: list[Article]) -> list[Article]:
    unique: list[Article] = []
    seen: set[str] = set()
    for article in articles:
        key = story_key(article)
        if key in seen:
            continue
        seen.add(key)
        unique.append(article)
    return unique


def story_key(article: Article) -> str:
    title = _normalize_for_key(article.title)
    if len(title) >= 12:
        return f"title:{title}"
    summary = _normalize_for_key(article.summary or article.content)
    return f"body:{title}:{summary[:140]}"


def topic_key(article: Article) -> str:
    text = _normalize(" ".join([article.title, article.summary, article.content]))
    known_topics = (
        ("eurovision", (r"\beurovision\b",)),
        ("cannes", (r"\bcannes\b", r"\bcroisette\b")),
        ("samsung-work", (r"\bsamsung\b",)),
        ("ukraine-war", (r"\bukraine\b",)),
        ("middle-east", (r"\bgaza\b", r"\bisrael\b", r"\bliban\b", r"\biran\b", r"\bfatah\b", r"\babbas\b", r"\bpalestin")),
        ("ebola", (r"\bebola\b",)),
        ("lgbt-rights", (r"\blgbt\b", r"\bhomophobie\b", r"\bdiscrimination\b")),
    )
    for key, patterns in known_topics:
        if _matches_any(text, patterns):
            return key
    words = [word for word in re.findall(r"[a-z0-9]{4,}", text) if word not in _TOPIC_STOP_WORDS]
    return "-".join(words[:4]) or text[:40]


_TOPIC_STOP_WORDS = {
    "avec",
    "dans",
    "pour",
    "plus",
    "tout",
    "tous",
    "toutes",
    "cette",
    "apres",
    "avant",
    "contre",
    "entre",
    "selon",
    "direct",
    "actualite",
    "france",
    "suisse",
}


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _normalize(text: str) -> str:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text


def _normalize_for_key(text: str) -> str:
    text = _normalize(text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
