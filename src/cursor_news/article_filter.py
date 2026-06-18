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
    r"\bworld cup\b",
    r"\bfifa\b",
    r"\buefa\b",
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
    r"\bhockeyeurs?\b",
    r"\bhockeyeuses?\b",
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
    r"\bteam ranked\b",
    r"\branked after first game\b",
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

LOW_VALUE_ARTICLE_PATTERNS = (
    r"^\W*en direct\b",
    r"\blive\b",
    r"\blatest news bulletin\b",
    r"\btaxi questions\b",
    r"\bfinale saison\b",
    r"\ba la une de la presse\b",
    r"\bvoir toutes les emissions\b",
    r"^(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+\d{1,2}[./-]\d{1,2}[./-]\d{4}$",
    r"^cin[eé]ma\s+\d{1,2}[./-]\d{1,2}[./-]\d{4}$",
    r"\bla parole est [aà] nous\b",
    r"\ble journal\s+(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)?\b",
    r"\bconnexion e-?mail\b",
    r"\bmot de passe\b",
    r"\bvoir toutes les [eé]missions\b",
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

TOPIC_PATTERNS: dict[str, tuple[str, ...]] = {
    "suisse_romande": (
        r"\bsuisse romande\b",
        r"\bromand",
        r"\bvaud\b",
        r"\bgen[eè]ve\b",
        r"\bfribourg\b",
        r"\bneuch[aâ]tel\b",
        r"\bjura\b",
        r"\bvalais\b",
        r"\blac du leman\b",
        r"\bleman\b",
    ),
    "valais": (
        r"\bvalais\b",
        r"\bvalaisan",
        r"\bwallis\b",
        r"\bsion\b",
        r"\bmartigny\b",
        r"\bsierre\b",
        r"\bmonthey\b",
        r"\bbrigue\b",
        r"\bbrig\b",
        r"\bvi[eè]ge\b",
        r"\bzermatt\b",
        r"\bverbier\b",
        r"\bchablais valaisan\b",
        r"\bhaut-valais\b",
        r"\bbas-valais\b",
    ),
    "suisse": (
        r"\bsuisse\b",
        r"\bconf[ée]d[ée]ration\b",
        r"\bconseil f[ée]d[ée]ral\b",
        r"\bparlement\b",
        r"\bberne\b",
        r"\bzurich\b",
        r"\bb[âa]le\b",
        r"\btessin\b",
        r"\bgrisons\b",
    ),
    "international": (
        r"\binternational\b",
        r"\bmonde\b",
        r"\beurope\b",
        r"\bukraine\b",
        r"\bgaza\b",
        r"\betats-unis\b",
        r"\bétats-unis\b",
        r"\bchine\b",
        r"\brussie\b",
        r"\bafrique\b",
    ),
    "un_relevant": (
        r"\bonu\b",
        r"\bnations unies\b",
        r"\bunited nations\b",
        r"\bsecurity council\b",
        r"\bconseil de s[ée]curit[ée]\b",
        r"\bhumanitarian\b",
        r"\bhuman rights\b",
        r"\bdroits humains\b",
        r"\br[ée]fugi[ée]",
        r"\bwho\b",
        r"\boms\b",
        r"\bunhcr\b",
        r"\bunicef\b",
        r"\bocha\b",
        r"\bpeacekeeping\b",
    ),
    "international_english": (
        r"\bworld\b",
        r"\binternational\b",
        r"\bglobal\b",
        r"\beurope\b",
        r"\bunited states\b",
        r"\bukraine\b",
        r"\bgaza\b",
        r"\brussia\b",
        r"\bchina\b",
        r"\bmiddle east\b",
    ),
    "security_world": (
        r"\bsecurity\b",
        r"\bs[ée]curit[ée]\b",
        r"\bwar\b",
        r"\bguerre\b",
        r"\bconflict\b",
        r"\bconflit\b",
        r"\battack\b",
        r"\battaque\b",
        r"\bmilitary\b",
        r"\barmy\b",
        r"\barm[ée]e\b",
        r"\bterror",
        r"\bhostage\b",
        r"\botage\b",
        r"\bsanction",
        r"\bcyber",
    ),
}


def is_sports_article(article: Article) -> bool:
    return is_sports_text(article.title, article.summary, article.content, article.source_name)


def is_sports_text(title: str, summary: str = "", content: str = "", source_name: str = "") -> bool:
    text = _normalize(" ".join([source_name, title, summary, content]))
    if _matches_any(text, SPORT_STRONG_PATTERNS):
        return True
    context_hits = sum(1 for pattern in SPORT_CONTEXT_PATTERNS if re.search(pattern, text))
    has_team = _matches_any(text, SPORT_TEAM_PATTERNS)
    return has_team and context_hits >= 1 or context_hits >= 3


def filter_sports_articles(articles: list[Article]) -> list[Article]:
    return [article for article in articles if not is_sports_article(article)]


def is_low_value_article(article: Article) -> bool:
    text = _normalize(" ".join([article.title, article.summary[:500]])).strip()
    return _matches_any(text, LOW_VALUE_ARTICLE_PATTERNS)


def filter_low_value_articles(articles: list[Article]) -> list[Article]:
    return [article for article in articles if not is_low_value_article(article)]


def is_child_unsuitable_article(article: Article) -> bool:
    text = _normalize(" ".join([article.title, article.summary, article.content]))
    return _matches_any(text, CHILD_UNSUITABLE_PATTERNS)


def filter_child_unsuitable_articles(articles: list[Article]) -> list[Article]:
    return [article for article in articles if not is_child_unsuitable_article(article)]


def anxiety_score(article: Article) -> int:
    text = _normalize(" ".join([article.title, article.summary, article.content]))
    return sum(2 for pattern in ANXIETY_STRONG_PATTERNS if re.search(pattern, text))


def _security_summary_score(normalized_text: str) -> int:
    return sum(2 for pattern in ANXIETY_STRONG_PATTERNS if re.search(pattern, normalized_text))


def calm_score(article: Article) -> int:
    text = _normalize(" ".join([article.title, article.summary, article.content]))
    return sum(1 for pattern in CALM_PATTERNS if re.search(pattern, text))


def rank_articles_for_style(articles: list[Article], style_key: str | None) -> list[Article]:
    return rank_articles_for_topic(articles, style_key)


def rank_articles_for_topic(articles: list[Article], topic_key: str | None) -> list[Article]:
    if topic_key in TOPIC_PATTERNS:
        return [
            article
            for _index, article in sorted(
                enumerate(articles),
                key=lambda item: (-topic_relevance_score(item[1], topic_key), -item[1].priority, item[0]),
            )
        ]
    if topic_key == "anxiogene":
        return [
            article
            for _index, article in sorted(
                enumerate(articles),
                key=lambda item: (-anxiety_score(item[1]), item[0]),
            )
        ]
    if topic_key == "non_anxiogene":
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


def topic_relevance_score(article: Article, topic_key: str | None) -> int:
    if not topic_key:
        return 0
    if topic_key == "security_world":
        text = _normalize(" ".join([article.source_name, article.region, article.title, article.summary]))
    else:
        text = _normalize(" ".join([article.source_name, article.region, article.title, article.summary, article.content]))
    source = _normalize(article.source_name)
    region = _normalize(article.region)
    score = 0
    for pattern in TOPIC_PATTERNS.get(topic_key, ()):
        if re.search(pattern, text):
            score += 4
    if topic_key == "suisse_romande":
        if region in {"suisse-romande", "valais"}:
            score += 14
        elif region == "suisse":
            score += 5
    elif topic_key == "valais":
        if region == "valais":
            score += 18
        if "valais" in source or "canal9" in source or "antenne region valais" in source:
            score += 12
    elif topic_key == "suisse":
        if region in {"suisse", "suisse-romande", "valais"}:
            score += 12
    elif topic_key == "international":
        if region in {"international", "europe"}:
            score += 12
        if region == "france":
            score += 2
    elif topic_key == "un_relevant":
        if source.startswith("un news"):
            score += 22
    elif topic_key == "international_english":
        if region == "english":
            score += 20
        if source.startswith("un news"):
            score += 4
    elif topic_key == "security_world":
        score += min(14, _security_summary_score(text) * 2)
        if region in {"english", "international", "europe"}:
            score += 6
    return score


def filter_articles_for_topic(articles: list[Article], topic_key: str | None, minimum: int = 4) -> list[Article]:
    if topic_key == "international_english":
        english = [article for article in articles if article.region == "english"]
        return english or articles
    if topic_key not in TOPIC_PATTERNS:
        return articles
    focused = [article for article in articles if topic_relevance_score(article, topic_key) > 0]
    if topic_key == "un_relevant":
        official_un = [article for article in focused if _normalize(article.source_name).startswith("un news")]
        return official_un
    if topic_key in {"international", "security_world"}:
        return focused
    return focused if len(focused) >= minimum else articles


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
