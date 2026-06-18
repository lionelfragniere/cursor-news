from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Protocol

import httpx

from .models import Article, BulletinDraft, StyleSlot


class LLMClient(Protocol):
    def generate_bulletin(self, articles: list[Article], style: StyleSlot, slot_start: datetime) -> BulletinDraft:
        ...


class OllamaLLMClient:
    def __init__(self, base_url: str, model: str, timeout_seconds: float = 180.0, json_format: bool = False):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.json_format = json_format

    def generate_bulletin(self, articles: list[Article], style: StyleSlot, slot_start: datetime) -> BulletinDraft:
        prompt = build_prompt(articles, style, slot_start)
        return self._generate_json(prompt, temperature=0.42, num_predict=2300)

    def revise_bulletin(
        self,
        draft: BulletinDraft,
        articles: list[Article],
        style: StyleSlot,
        slot_start: datetime,
        issue: str,
    ) -> BulletinDraft:
        prompt = build_revision_prompt(draft, articles, style, slot_start, issue)
        revised = self._generate_json(prompt, temperature=0.36, num_predict=2300)
        return BulletinDraft(
            title=revised.title,
            summary=revised.summary,
            transcript=revised.transcript,
            warnings=[*draft.warnings, *revised.warnings, f"Revision automatique apres controle qualite: {issue}"],
        )

    def _generate_json(self, prompt: str, temperature: float, num_predict: int) -> BulletinDraft:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "num_ctx": 8192,
                "num_predict": num_predict,
                "top_p": 0.9,
                "repeat_penalty": 1.08,
            },
        }
        if self.json_format:
            payload["format"] = "json"
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
        raw = response.json().get("response", "")
        return BulletinDraft.from_mapping(parse_json_object(raw))


class TemplateLLMClient:
    """Deterministic local client used for tests and dry development."""

    def generate_bulletin(self, articles: list[Article], style: StyleSlot, slot_start: datetime) -> BulletinDraft:
        if not articles:
            return fallback_bulletin(style)
        opener = _template_opener(style)
        lines = [opener]
        selected_articles = articles[:12]
        for index, article in enumerate(selected_articles, start=1):
            text = article.summary or article.content or article.title
            text = " ".join(text.split())
            lines.append(_template_segment(style, index, article.title, article.source_name, text))
        lines.append(_template_closer(style))
        lines.append(_source_credit(selected_articles, language=style.language))
        transcript = "\n\n".join(lines)
        return BulletinDraft(
            title=f"Cursor News - {style.label}",
            summary=(
                f"{len(articles)} articles summarized locally."
                if style.language == "en"
                else f"{len(articles)} articles résumés localement."
            ),
            transcript=transcript,
            warnings=["Sortie générée par le moteur template, sans LLM."],
        )


_FRENCH_ACCENT_REPLACEMENTS = (
    ("Edition speciale", "Édition spéciale"),
    ("edition speciale", "édition spéciale"),
    ("edition", "édition"),
    ("editions", "éditions"),
    ("actualite", "actualité"),
    ("actualites", "actualités"),
    ("consequence", "conséquence"),
    ("consequences", "conséquences"),
    ("securite", "sécurité"),
    ("sante", "santé"),
    ("economie", "économie"),
    ("economique", "économique"),
    ("economiques", "économiques"),
    ("merite", "mérite"),
    ("deja", "déjà"),
    ("detecte", "détecté"),
    ("detectee", "détectée"),
    ("element", "élément"),
    ("elements", "éléments"),
    ("redaction", "rédaction"),
    ("resume", "résumé"),
    ("resumes", "résumés"),
    ("genere", "génère"),
    ("generee", "générée"),
    ("verifie", "vérifie"),
    ("verifies", "vérifiés"),
    ("verifier", "vérifier"),
    ("verifiera", "vérifiera"),
    ("ecoute", "écoute"),
    ("ecoutez", "écoutez"),
    ("francais", "français"),
    ("Francais", "Français"),
    ("Liberation", "Libération"),
    ("creneau", "créneau"),
    ("cafe", "café"),
    ("des que", "dès que"),
    ("a l'antenne", "à l'antenne"),
    ("a comprendre", "à comprendre"),
    ("a surveiller", "à surveiller"),
    ("a suivre", "à suivre"),
)


def repair_french_accents(text: str) -> str:
    """Repair common accent omissions in generated French radio copy."""
    for source, target in _FRENCH_ACCENT_REPLACEMENTS:
        text = re.sub(rf"\b{re.escape(source)}\b", target, text)
    return text


def repair_bulletin_french_accents(draft: BulletinDraft) -> BulletinDraft:
    return BulletinDraft(
        title=repair_french_accents(draft.title),
        summary=repair_french_accents(draft.summary),
        transcript=repair_french_accents(draft.transcript),
        warnings=draft.warnings,
    )


def enforce_source_credit_at_end(draft: BulletinDraft, articles: list[Article], language: str = "fr") -> BulletinDraft:
    transcript = draft.transcript.strip()
    for article in articles:
        transcript = _remove_source_references(transcript, article.source_name, preserve_newlines=True)
    transcript = re.sub(r"\n*\s*Sources utilisées pour cette édition\s*:.*$", "", transcript, flags=re.S)
    transcript = re.sub(r"\n*\s*Sources used for this edition\s*:.*$", "", transcript, flags=re.S | re.I)
    transcript = _remove_meta_fillers(transcript)
    transcript = _format_body_paragraphs(transcript)
    if articles:
        transcript = f"{transcript}\n\n{_source_credit(articles, language=language)}"
    return BulletinDraft(
        title=draft.title,
        summary=draft.summary,
        transcript=transcript,
        warnings=draft.warnings,
    )


def build_prompt(articles: list[Article], style: StyleSlot, slot_start: datetime) -> str:
    article_block = _article_block(articles)
    language = getattr(style, "language", "fr")
    if language == "en":
        return _build_english_prompt(article_block, style, slot_start)
    return _build_french_prompt(article_block, style, slot_start)


def build_revision_prompt(
    draft: BulletinDraft,
    articles: list[Article],
    style: StyleSlot,
    slot_start: datetime,
    issue: str,
) -> str:
    article_block = _article_block(articles)
    original = draft.transcript.strip()
    if getattr(style, "language", "fr") == "en":
        return f"""
You are the senior editor of Cursor News. A first draft failed the quality check: {issue}

Rewrite the bulletin from scratch as a fluent public-service radio script in English.

Mandatory constraints:
- Keep only facts supported by the source pack.
- Keep the same topic: {style.label}.
- Write 900 to 1250 words, with 6 to 9 developed items.
- The script will be read aloud by text-to-speech: use clear punctuation, natural rhythm, and no bullet points.
- Do not read RSS headlines as section titles. Turn them into spoken leads.
- Do not mention media names inside the body. Put source credits only in the final sentence.
- Avoid repeated paragraph openings and generic filler.
- Output valid JSON only.

Slot: {slot_start.isoformat()}
Editorial brief: {style.prompt}

Source pack:
{article_block}

First draft to replace:
{original}

JSON shape:
{{
  "title": "short title",
  "summary": "one-sentence summary",
  "transcript": "full script to read on air",
  "warnings": []
}}

/no_think
""".strip()
    return f"""
Tu es la rédactrice en chef de Cursor News. Un premier texte a échoué au contrôle qualité: {issue}

Réécris entièrement le bulletin en français naturel, comme un vrai script radio de service public.

Contraintes obligatoires:
- Garde uniquement les faits présents dans le paquet de sources.
- Garde le même sujet: {style.label}.
- Écris 900 à 1250 mots, avec 6 à 9 sujets développés.
- Le texte sera lu à voix haute par une synthèse vocale: ponctuation claire, rythme naturel, phrases pas trop longues.
- Ne lis pas les titres RSS comme des intertitres. Transforme-les en lancements parlés.
- Ne cite aucun média dans le corps du bulletin. Les sources vont seulement dans la toute dernière phrase.
- Évite les débuts de paragraphes répétitifs et les phrases de remplissage.
- Réponds uniquement en JSON valide.

Créneau: {slot_start.isoformat()}
Consigne éditoriale: {style.prompt}

Paquet de sources:
{article_block}

Premier texte à remplacer:
{original}

Forme JSON:
{{
  "title": "titre court",
  "summary": "résumé en une phrase",
  "transcript": "texte complet à lire à l'antenne",
  "warnings": []
}}

/no_think
""".strip()


def _build_french_prompt(article_block: str, style: StyleSlot, slot_start: datetime) -> str:
    guidance = _subject_guidance(style)
    return f"""
Tu es la rédactrice en chef et présentatrice de Cursor News, un flash radio d'actualité pour la Suisse romande.

Le texte sera lu tel quel par une voix de synthèse. Écris donc pour l'oreille: phrases nettes, ponctuation utile, transitions naturelles, aucune mise en page destinée à être vue.

Créneau: {slot_start.isoformat()}
Sujet du flash: {style.label}
Consigne éditoriale: {style.prompt}
Angle spécifique: {guidance}

Mission:
- Produire un bulletin d'environ 8 minutes, entre 980 et 1240 mots.
- Choisir 6 à 9 sujets maximum dans le paquet de sources. Ignore les articles faibles, doublons ou hors sujet.
- Ouvrir par une accroche sobre qui donne l'angle du bulletin, pas par une formule générique.
- Pour chaque sujet: lancer l'information, expliquer le contexte utile, puis dire pourquoi cela compte ou ce qu'il faut surveiller.
- Écrire comme une journaliste radio: fluide, incarné, précis, mais sans dramatiser.
- Ne pas réciter les titres RSS. Les titres servent à comprendre le sujet, pas à être lus tels quels.
- Ne pas empiler "D'abord", "Ensuite", "Autre point" à chaque paragraphe. Varie les transitions et laisse respirer le texte.
- Ne pas inventer de chiffres, dates, citations, causalités ou réactions absentes des sources.
- Distinguer clairement ce qui est confirmé, annoncé, prévu, contesté ou encore incertain.
- Exclure le sport strict: résultats, matches, transferts, entraîneurs, compétitions, classements.
- Ne cite aucun média dans les sujets: pas de "selon", pas de "source:", pas de nom de journal dans les transitions.
- Mets les crédits de sources uniquement dans la dernière phrase, exactement sous la forme: "Sources utilisées pour cette édition: ...".
- Termine par une conclusion courte qui ferme le flash sans slogan.

Interdits de style:
- Pas de numérotation visible: "Point 1", "Sujet 1", "Alerte 1".
- Pas de phrases méta ou creuses: "il y a une situation à comprendre", "dit simplement", "l'enjeu maintenant", "ce dossier montre que".
- Pas de paragraphe qui se contente de répéter une catégorie comme "une information culturelle" ou "des responsables prennent des décisions".
- Pas de markdown, pas de listes à puces, pas d'indications de respiration ou de régie.

Paquet de sources:
{article_block}

Réponds uniquement en JSON valide avec cette forme:
{{
  "title": "titre court",
  "summary": "résumé en une phrase",
  "transcript": "texte complet à lire à l'antenne",
  "warnings": []
}}

/no_think
""".strip()


def _build_english_prompt(article_block: str, style: StyleSlot, slot_start: datetime) -> str:
    guidance = _subject_guidance(style)
    return f"""
You are the senior editor and presenter of Cursor News, a concise public-service radio briefing.

The transcript will be read aloud by text-to-speech. Write for the ear: clean sentences, natural rhythm, useful punctuation, and no visual formatting.

Slot: {slot_start.isoformat()}
Briefing topic: {style.label}
Editorial brief: {style.prompt}
Specific angle: {guidance}

Mission:
- Produce an eight-minute briefing, between 980 and 1240 words.
- Select 6 to 9 items from the source pack. Ignore weak, duplicate, or off-topic items.
- Open with a focused radio lead, not a generic greeting.
- For each item: state the news, give the useful context, then explain why it matters or what to watch next.
- Sound like a public-service radio journalist: fluent, precise, calm, and factual.
- Do not read RSS headlines as section titles. Use them only to understand the story.
- Do not start every paragraph with "First", "Next", or "Also". Vary the transitions and let the script breathe.
- Do not invent numbers, dates, quotes, causes, or reactions that are not in the sources.
- Clearly separate confirmed facts, announcements, plans, disputed claims, and uncertainties.
- Exclude pure sports stories: results, matches, transfers, coaches, competitions, rankings.
- Do not mention media names in the body: no "according to", no "source:", no outlet name in transitions.
- Put source credits only in the final sentence, exactly as: "Sources used for this edition: ...".
- Finish with a short closing line, without a slogan.

Style bans:
- No visible numbering: "Point 1", "Item 1", "Alert 1".
- No generic filler: "the key issue now", "this is a situation to understand", "in simple terms".
- No paragraph that only repeats a category such as "this is cultural news" or "leaders are making decisions".
- No markdown, no bullet points, no production notes.

Source pack:
{article_block}

Return valid JSON only, in this shape:
{{
  "title": "short title",
  "summary": "one-sentence summary",
  "transcript": "full script to read on air",
  "warnings": []
}}

/no_think
""".strip()


def _article_block(articles: list[Article]) -> str:
    return "\n\n".join(_article_prompt_text(index, article) for index, article in enumerate(articles, start=1))


def _article_prompt_text(index: int, article: Article) -> str:
    body = article.content or article.summary
    body = " ".join(body.split())
    if len(body) > 900:
        body = body[:900].rsplit(" ", 1)[0] + "..."
    return (
        f"Article A{index:02d}\n"
        f"- Source: {article.source_name}\n"
        f"- Region: {article.region}\n"
        f"- Detected language: {article.language}\n"
        f"- Title: {article.title}\n"
        f"- URL: {article.url}\n"
        f"- Date: {article.published_at or 'unknown'}\n"
        f"- Content: {body}"
    )


def _subject_guidance(style: StyleSlot) -> str:
    match style.key:
        case "suisse_romande":
            return "Priorise les effets concrets pour les cantons romands, les services publics, l'économie locale, les transports, la santé, l'école et la vie culturelle."
        case "valais":
            return "Garde une focale valaisanne: communes, canton, montagne, énergie, climat, tourisme, infrastructures, santé et décisions politiques locales."
        case "suisse":
            return "Explique ce qui change à l'échelle fédérale et pourquoi cela peut concerner la Suisse romande."
        case "international":
            return "Sélectionne les grands faits mondiaux utiles à comprendre depuis la Suisse romande, avec du contexte plutôt qu'une simple succession de pays."
        case "un_relevant":
            return "Keep the briefing in English and connect the news to UN agencies, humanitarian access, human rights, peace and security, global health, refugees, climate, or multilateral diplomacy when relevant."
        case "international_english":
            return "Keep the briefing in English and focus on major global developments with clear context for listeners following international affairs."
        case "security_world":
            return "Couvre les risques de sécurité sans sensationnalisme: conflits, crises humanitaires, cybermenaces, tensions militaires, sécurité civile et décisions diplomatiques."
        case _:
            return "Reste centré sur le sujet annoncé et privilégie les informations les plus utiles pour l'auditeur."


def parse_json_object(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise


def fallback_bulletin(style: StyleSlot) -> BulletinDraft:
    if style.language == "en":
        return BulletinDraft(
            title=f"Cursor News - waiting for {style.label}",
            summary="No reliable new item is available for this slot.",
            transcript=(
                "You are listening to Cursor News. For this slot, no reliable source item is ready yet. "
                "The automatic newsroom keeps monitoring the feeds and will return with a new edition "
                "as soon as verified information is available."
            ),
            warnings=["Fallback without a new article."],
        )
    transcript = (
        "Vous écoutez Cursor News. Pour ce créneau, aucune nouvelle source exploitable "
        "n'a été détectée. La rédaction automatique continue de surveiller les flux RSS "
        "et revient avec une nouvelle édition dès qu'une information fiable est disponible."
    )
    return BulletinDraft(
        title=f"Cursor News - attente {style.label}",
        summary="Aucune nouvelle actualité exploitable pour ce créneau.",
        transcript=transcript,
        warnings=["Fallback sans article nouveau."],
    )


def _template_opener(style: StyleSlot) -> str:
    if style.language == "en":
        if style.key == "un_relevant":
            return "You are listening to Cursor News. Here is the United Nations briefing, with the facts, the humanitarian context, and what to watch next."
        return "You are listening to Cursor News. Here is the international briefing in English, with the facts, the context, and what to watch next."
    match style.key:
        case "suisse_romande":
            return "Bonjour, vous écoutez Cursor News. Voici le point sur les informations qui comptent en Suisse romande, avec les faits utiles et le contexte local."
        case "valais":
            return "Bonjour, vous écoutez Cursor News. Ce bulletin se concentre sur le Valais, ses communes, ses institutions et les sujets qui touchent directement la région."
        case "suisse":
            return "Bonjour, vous écoutez Cursor News. Voici le tour d'horizon suisse, des décisions fédérales aux sujets qui peuvent peser sur la vie quotidienne."
        case "international":
            return "Bonjour, vous écoutez Cursor News. On prend maintenant de la hauteur avec les principales nouvelles internationales à suivre depuis la Suisse romande."
        case "un_relevant":
            return "Bonjour, vous écoutez Cursor News. Ce point suit les nouvelles importantes pour les Nations Unies, l'humanitaire, les droits humains, la paix et la sécurité."
        case "security_world":
            return "Bonjour, vous écoutez Cursor News. Voici le point sur la situation sécuritaire mondiale, avec prudence, contexte et faits vérifiés."
        case "pote":
            return "Salut, c'est Cursor News. On prend quelques minutes pour faire le tour des infos qui comptent, sans jargon et sans tourner autour du pot."
        case "non_anxiogene":
            return "Bienvenue sur Cursor News. Dans cette édition calme, on garde le cap sur les faits, les repères utiles et ce qui permet de comprendre sans dramatiser."
        case "anxiogene":
            return "Édition spéciale Cursor News. Le rythme est plus tendu ce soir: on suit les signaux d'alerte, les risques possibles et les conséquences concrètes, sans sortir des faits établis."
        case "enfant":
            return "Bonjour, tu écoutes Cursor News. On reprend les grandes nouvelles avec des mots simples, pour comprendre ce qui se passe sans se perdre dans les détails compliqués."
        case "contexte":
            return "Bonjour, vous écoutez Cursor News. Dans cette édition de fin d'heure, on prend un peu de recul: ce qui vient de se passer, ce que cela change, et ce qu'il faudra suivre ensuite."
        case _:
            return "Bonjour, vous écoutez Cursor News. Voici les principales actualités francophones et internationales, avec un point clair sur les faits et leurs conséquences."


def _template_segment(style: StyleSlot, index: int, title: str, source: str, text: str) -> str:
    excerpt = _word_limit(_clean_article_text(text, source), 115)
    transition = _transition_for(index)
    context = _template_context_sentence(style, index)
    context_suffix = f" {context}" if context else ""
    if style.language == "en":
        return (
            f"{_english_transition_for(index)}, {title}. "
            f"{_sentence(excerpt)}{context_suffix}"
        )
    match style.key:
        case "pote":
            return (
                f"{transition}, {title}. "
                f"En clair, {_sentence(_lower_initial_for_flow(excerpt))}"
            )
        case "non_anxiogene":
            return (
                f"{transition}, {title}. "
                f"{_sentence(excerpt)}"
            )
        case "anxiogene":
            return (
                f"{transition}, {title}. "
                f"{_sentence(excerpt)}"
            )
        case "enfant":
            return _template_child_segment(index, title, source, text)
        case "contexte":
            return (
                f"{transition}, {title}. "
                f"{_sentence(excerpt)} "
                "À suivre maintenant: les réactions, les décisions concrètes et les effets possibles pour le public romand."
            )
        case _:
            return (
                f"{transition}, {title}. "
                f"{_sentence(excerpt)}{context_suffix}"
            )


def _template_context_sentence(style: StyleSlot, index: int) -> str:
    if style.language == "en":
        if style.key == "un_relevant":
            options = [
                "For the UN system, the key question is how this affects protection, access, funding, or diplomatic coordination.",
                "The next signal to watch is whether agencies, member states, and local partners can turn statements into practical action.",
                "For listeners following multilateral affairs, the useful marker is what changes for civilians and field operations.",
            ]
        else:
            options = [
                "The next signal to watch is how institutions respond, and whether the situation widens beyond the first announcements.",
                "The broader question is whether this becomes a short news cycle or a decision point for diplomacy, aid, or security policy.",
                "For listeners following international affairs, the useful marker is what changes on the ground, not only what leaders say.",
            ]
    elif style.key == "un_relevant":
        options = [
            "Ce dossier comptera surtout par ses effets sur l'aide humanitaire, les droits humains ou la diplomatie multilatérale.",
            "La suite dépendra des décisions prises par les autorités concernées, les agences internationales et les partenaires sur le terrain.",
            "Pour les organisations internationales, l'élément à suivre sera la capacité de coordination et de protection des personnes touchées.",
        ]
    elif style.key == "security_world":
        options = [
            "Le point à suivre est l'évolution du risque réel, loin des déclarations les plus bruyantes.",
            "Dans les prochaines heures, les confirmations indépendantes seront plus importantes que les premières réactions politiques.",
            "Ce dossier demande de surveiller les faits établis, les déplacements de population et les décisions de sécurité concrètes.",
        ]
    elif style.key == "valais":
        options = [
            "Pour le Valais, l'intérêt se joue dans les conséquences concrètes pour les communes, les habitants ou les acteurs économiques.",
            "La suite dira si le sujet reste local ou s'il prend une portée plus large dans le canton.",
            "On suivra les réponses des autorités et les effets pratiques pour les personnes directement concernées.",
        ]
    elif style.key in {"suisse_romande", "suisse", "international"}:
        options = [
            "La suite se jouera dans les décisions attendues et dans leurs effets concrets pour le public.",
            "Le repère utile sera de distinguer les faits confirmés des réactions qui peuvent encore évoluer.",
            "Cursor News suivra surtout ce que cette information change dans les prochaines heures.",
        ]
    else:
        return ""
    return options[(index - 1) % len(options)]


def _template_closer(style: StyleSlot) -> str:
    if style.language == "en":
        return "That is the end of this Cursor News briefing. We will keep following the verified updates for the next edition."
    match style.key:
        case "suisse_romande" | "valais" | "suisse":
            return "C'est la fin de ce bulletin. Cursor News continue de suivre ces dossiers et revient avec les prochains éléments confirmés."
        case "international" | "un_relevant" | "security_world":
            return "C'est la fin de ce point. Cursor News garde ces dossiers ouverts et reviendra avec les développements confirmés."
        case "pote":
            return "Voilà pour ce tour d'horizon. On garde l'oeil ouvert, et on se retrouve au prochain bulletin Cursor News."
        case "non_anxiogene":
            return "Fin de cette édition apaisée. Les faits importants sont posés, et Cursor News continue de suivre les développements pour la prochaine tranche."
        case "anxiogene":
            return "Fin de cette édition sous tension. Les signaux restent à surveiller, et Cursor News revient dès que de nouveaux éléments solides apparaissent."
        case "enfant":
            return "C'est la fin de ce bulletin. On se retrouve au prochain rendez-vous Cursor News."
        case "contexte":
            return "Fin de ce point de contexte. Cursor News garde ces dossiers ouverts et revient au prochain créneau avec les éléments nouveaux, confirmés et utiles."
        case _:
            return "C'était Cursor News. Merci pour votre écoute, et rendez-vous dans quelques minutes pour la prochaine édition."


def _transition_for(index: int) -> str:
    transitions = [
        "D'abord",
        "Ensuite",
        "En parallèle",
        "À suivre également",
        "Autre point important",
        "Dans le reste de l'actualité",
        "Plus loin dans ce bulletin",
        "Autre information à retenir",
        "Dernier point",
        "Pour finir",
    ]
    return transitions[min(index, len(transitions)) - 1]


def _english_transition_for(index: int) -> str:
    transitions = [
        "First",
        "Next",
        "In parallel",
        "Also worth noting",
        "Another important point",
        "Elsewhere",
        "Further in this briefing",
        "Another item to watch",
        "One final point",
        "To close",
    ]
    return transitions[min(index, len(transitions)) - 1]


def _source_credit(articles: list[Article], language: str = "fr") -> str:
    sources = []
    for article in articles:
        if article.source_name not in sources:
            sources.append(article.source_name)
    if language == "en":
        return "Sources used for this edition: " + ", ".join(sources) + "."
    return "Sources utilisées pour cette édition: " + ", ".join(sources) + "."


def _template_child_segment(index: int, title: str, source: str, text: str) -> str:
    transition = _transition_for(index)
    clean_title = _clean_child_title(title)
    kind = _child_topic_kind(clean_title, text)
    subject = _child_concrete_subject(clean_title, kind)
    detail = _child_concrete_detail(clean_title, text, source, kind)
    return f"{transition}, {subject}. {detail}"


def _clean_child_title(title: str) -> str:
    clean = title.strip()
    clean = re.sub(r"^\s*(EN DIRECT|DIRECT|VIDÉO|VIDEO|INFO)\s*[,:\-]\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*;\s*(au moins|plus de|près de|pres de|\d+)\b.*$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s+", " ", clean)
    clean = _child_simplify_text(clean)
    return _sentence(clean.strip(" .")).rstrip(".")


def _child_topic_kind(title: str, text: str) -> str:
    title_normalized = _normalize_for_rules(title)
    normalized = _normalize_for_rules(f"{title} {text}")
    if any(word in title_normalized for word in ("cannes", "film", "cinema", "musique", "eurovision", "documentaire", "festival", "spectacle")):
        return "culture"
    if any(word in title_normalized for word in ("science", "chercheur", "intelligence artificielle", "neandertal", "decouverte")):
        return "science"
    if any(word in title_normalized for word in ("greve", "salaries", "entreprise", "travail", "samsung")):
        return "work"
    if any(word in title_normalized for word in ("ebola", "epidemie", "oms", "virus", "sante", "hantavirus")):
        return "health"
    if any(word in title_normalized for word in ("lgbt", "homophobie", "discrimination")):
        return "rights"
    if any(word in title_normalized for word in ("guerre", "gaza", "ukraine", "liban", "iran", "israel", "moyen-orient", "drones", "bombard")):
        return "conflict"
    if any(word in title_normalized for word in ("president", "ministre", "parlement", "gouvernement", "justice", "election", "senat", "fatah")):
        return "politics"
    if any(word in normalized for word in ("ebola", "epidemie", "oms", "virus")):
        return "health"
    if any(word in normalized for word in ("guerre", "gaza", "ukraine", "liban", "iran", "moyen-orient", "drones", "bombard")):
        return "conflict"
    return "general"


def _child_concrete_subject(title: str, kind: str) -> str:
    normalized = _normalize_for_rules(title)
    if "darmanin" in normalized or "algerie" in normalized:
        return "la France et l'Algérie discutent de justice"
    if "pape leon" in normalized or "pape léon" in normalized:
        return "le pape Léon XIV prépare une visite en France"
    if "robots" in normalized or "noa" in normalized or "niko" in normalized:
        return "de nouveaux robots de compagnie arrivent dans les magasins"
    if kind == "culture":
        if "bandes-annonces" in normalized or "affiches" in normalized:
            return "au cinéma, les bandes-annonces et les affiches changent"
        if "eurovision" in normalized:
            if "bulgarie" in normalized or "bulgare" in normalized:
                return "à l'Eurovision, la Bulgarie gagne pour la première fois"
            return _lower_initial_for_flow(re.sub(r"^Eurovision\s*:\s*", "à l'Eurovision, ", title, flags=re.IGNORECASE))
        if "cannes" in normalized:
            return "au Festival de Cannes, de nouveaux films font parler"
        return _lower_initial_for_flow(title)
    if kind == "work" and "samsung" in normalized:
        return "en Corée du Sud, des employés de Samsung font grève"
    if kind == "health" and "ebola" in normalized:
        return "des médecins surveillent l'épidémie d'Ebola"
    if kind == "health" and "hantavirus" in normalized:
        return "des médecins surveillent un virus détecté pendant un voyage"
    if kind == "conflict":
        if "ukraine" in normalized:
            return "en Ukraine, la guerre continue et perturbe la vie des habitants"
        if any(word in normalized for word in ("gaza", "liban", "israel", "iran", "moyen-orient")):
            return "au Moyen-Orient, les tensions restent fortes"
        return "un conflit continue de peser sur des familles"
    if kind == "politics":
        if "fatah" in normalized or "abbas" in normalized:
            return "dans les territoires palestiniens, le Fatah change une partie de son équipe dirigeante"
        if "etats-unis" in normalized or "états-unis" in normalized:
            return "aux États-Unis, une décision ou une élection change la vie politique"
        return _lower_initial_for_flow(title)
    if kind == "rights":
        return _lower_initial_for_flow(title)
    return _lower_initial_for_flow(title)


def _child_concrete_detail(title: str, text: str, source: str, kind: str) -> str:
    known_detail = _child_known_detail(title, text)
    if known_detail:
        return known_detail
    excerpt = _child_detail_excerpt(title, text, source)
    if kind == "conflict":
        return (
            "Les familles cherchent surtout à rester en sécurité, "
            "et les organisations d'aide essaient d'apporter de l'eau, de la nourriture ou des soins."
        )
    if kind == "health":
        if excerpt:
            return _sentence(excerpt)
        return (
            "Les médecins repèrent les personnes malades, les soignent et essaient d'empêcher la maladie de voyager trop loin."
        )
    if kind == "work":
        if excerpt:
            return _sentence(excerpt)
        return "Les salariés demandent de meilleures conditions de travail dans une grande entreprise connue dans le monde entier."
    if kind == "politics":
        if excerpt:
            return _sentence(excerpt)
        return "Cette décision peut changer l'organisation d'un pays ou la façon dont ses responsables travaillent ensemble."
    if kind == "rights":
        if excerpt:
            return _sentence(excerpt)
        return "Le coeur du sujet, c'est le respect et la sécurité des personnes dans la vie de tous les jours."
    if kind == "culture":
        if excerpt:
            return _sentence(excerpt)
        return "Le public réagit à une chanson, un film ou un spectacle, et cela montre quelles histoires intéressent les gens."
    if kind == "science":
        if excerpt:
            return _sentence(excerpt)
        return "Des chercheurs observent des indices et comparent leurs résultats pour mieux expliquer le monde."
    return _sentence(excerpt or title)


def _child_known_detail(title: str, text: str) -> str:
    normalized = _normalize_for_rules(f"{title} {text}")
    if "darmanin" in normalized or "algerie" in normalized:
        return (
            "Les deux pays doivent parler de coopération judiciaire. Cela veut dire qu'ils cherchent à mieux travailler ensemble sur certains dossiers compliqués. "
            "La coopération judiciaire concerne la manière dont deux pays partagent des informations pour aider les tribunaux."
        )
    if "pape leon" in normalized or "pape léon" in normalized:
        return (
            "Il doit venir en France en septembre. Pour beaucoup de croyants, cette visite aura une forte valeur symbolique."
        )
    if "robots" in normalized or "noa" in normalized or "niko" in normalized:
        return (
            "Ces petits robots sont pensés pour tenir compagnie et réagir aux personnes autour d'eux. Ils montrent comment la technologie entre peu à peu dans la maison. "
            "Cela pose aussi une question simple: comment utiliser ces machines sans remplacer les vraies relations humaines."
        )
    if "eurovision" in normalized:
        details = []
        if "bulgarie" in normalized or "bulgare" in normalized or "dara" in normalized:
            details.append("La chanteuse bulgare Dara a remporté le concours avec une chanson très énergique")
        if "france" in normalized:
            details.append("la France termine plus loin dans le classement")
        if "israel" in normalized:
            details.append("Israël arrive aussi en haut du classement, dans un contexte de désaccords")
        if details:
            return (
                f"{_join_child_clauses(details)} "
                "L'Eurovision est un concours où plusieurs pays présentent une chanson, puis obtiennent des points."
            )
        return "Cette soirée musicale réunit plusieurs pays, avec des chansons très différentes et un classement final."
    if "hantavirus" in normalized:
        return (
            "Une passagère est suivie par des médecins après un test inquiétant. Les autres personnes du voyage sont surveillées par prudence. "
            "Cela ne veut pas dire que tout le monde est malade: c'est surtout une mesure pour vérifier et éviter que le virus circule."
        )
    if "bandes-annonces" in normalized or "affiches" in normalized:
        return (
            "Certaines bandes-annonces montrent beaucoup d'images du film, et des affiches peuvent maintenant être aidées par l'intelligence artificielle."
        )
    if "cannes" in normalized:
        return (
            "Des films sont présentés au public et aux critiques. Certains plaisent beaucoup, d'autres font discuter, et c'est aussi cela qui fait vivre le festival. "
            "Le cinéma sert ici à raconter des histoires, mais aussi à provoquer des conversations."
        )
    if "samsung" in normalized or "greve" in normalized:
        return (
            "Les salariés demandent de meilleures conditions de travail. Ils veulent être entendus par une très grande entreprise connue dans le monde entier. "
            "Quand des salariés font grève, ils arrêtent le travail pour demander une vraie discussion."
        )
    if "fatah" in normalized or "abbas" in normalized:
        return (
            "Yasser Abbas entre dans un groupe important du mouvement politique Fatah. Cela compte surtout pour l'organisation de la politique palestinienne. "
            "Ce genre de changement peut influencer les décisions prises plus tard par un mouvement politique."
        )
    if "bill cassidy" in normalized or "louisiane" in normalized:
        return (
            "Un responsable républicain a perdu une élection interne. Ce résultat change les rapports de force dans son parti, dans l'État de Louisiane. "
            "Une élection interne sert à choisir quelle personne représentera un parti lors d'une prochaine étape politique."
        )
    return ""


def _join_child_clauses(clauses: list[str]) -> str:
    if not clauses:
        return ""
    if len(clauses) == 1:
        return _sentence(clauses[0])
    if len(clauses) == 2:
        return _sentence(f"{clauses[0]}, et {clauses[1]}")
    first, *rest = clauses
    rest_sentence = ", et ".join(rest)
    return f"{_sentence(first)} {_sentence(_upper_initial(rest_sentence))}"


def _child_detail_excerpt(title: str, text: str, source: str) -> str:
    cleaned = _clean_article_text(text, source)
    cleaned = _child_simplify_text(cleaned)
    cleaned = re.sub(r"^\s*(EN DIRECT|DIRECT|VIDÉO|VIDEO|INFO)\s*[,:\-]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        return ""
    title_norm = _normalize_for_rules(title)
    cleaned_norm = _normalize_for_rules(cleaned)
    if cleaned_norm == title_norm or cleaned_norm in title_norm:
        return ""
    return _word_limit(cleaned, 44)


def _child_simplify_text(text: str) -> str:
    replacements = (
        (r"\bbombardements?\b", "attaques"),
        (r"\bfrappes?\b", "attaques"),
        (r"\bdrones?\b", "appareils volants"),
        (r"\bdécès\b", "personnes touchées"),
        (r"\bmorts?\b", "personnes touchées"),
        (r"\bblessés?\b", "personnes blessées"),
        (r"\bautorités\b", "responsables"),
        (r"\bprésidentielle\b", "élection du président"),
        (r"\bprochaines étapes\b", "ce qui va se passer ensuite"),
        (r"\bgéant coréen\b", "grande entreprise"),
        (r"\bdu grande entreprise\b", "de la grande entreprise"),
        (r"\bprimaire sénatoriale\b", "élection interne pour le Sénat"),
        (r"\bboycott\b", "désaccord"),
        (r"\bcompète\b", "compétition"),
        (r"\bpoids lourds\b", "grands noms"),
        (r"\bhuent\b", "critiquent"),
        (r"\bdégringole\b", "descend"),
        (r"\bsurvitaminé\b", "très énergique"),
        (r"\bsans précédent\b", "très rare"),
        (r"\bscrutin\b", "vote"),
        (r"\béchiquier politique\b", "monde politique"),
        (r"\bCroisette\b", "Festival de Cannes"),
    )
    for source, target in replacements:
        text = re.sub(source, target, text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\s+appareils volants\b", "des appareils volants", text, flags=re.IGNORECASE)
    text = re.sub(r"\bau moins\s+\d+[^.,;]*", "plusieurs personnes", text, flags=re.IGNORECASE)
    text = re.sub(r"\bplus de\s+\d+[^.,;]*", "beaucoup de personnes", text, flags=re.IGNORECASE)
    return text


def _clean_article_text(text: str, source: str) -> str:
    text = _remove_source_references(text, source)
    text = re.sub(r"\bPar\s+[A-ZÉÈÀÂÊÎÔÛÇ][^.,:;]{0,80}\s+©\s+\d{4}\s+AFP\s*", "", text)
    text = re.sub(r"^Par\s+[^.]{3,100}?\s+(?=[A-ZÉÈÀÂÊÎÔÛÇ])", "", text)
    text = re.sub(r"\b[A-ZÉÈÀÂÊÎÔÛÇ][A-Za-zÀ-ÿ' -]{2,70}\s+avec agences\s+", "", text)
    text = re.sub(r"\bPar\s+[A-ZÉÈÀÂÊÎÔÛÇ][A-Za-zÀ-ÿ' -]{2,90}\s+avec agences\s+", "", text)
    text = re.sub(r"\bTV5\s+JWPlayer\s+Field\b", "", text)
    text = re.sub(r"©\s+\d{4}\s+AFP\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .")


def _remove_source_references(text: str, source: str, preserve_newlines: bool = False) -> str:
    for alias in _source_aliases(source):
        name = re.escape(alias)
        text = re.sub(rf"\bSelon\s+[«\"]?{name}[»\"]?\s*,?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(rf"\bD['’]après\s+[«\"]?{name}[»\"]?\s*,?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(rf"\bChez\s+[«\"]?{name}[»\"]?\s*,?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(rf"\bSource\s*:\s*[«\"]?{name}[»\"]?\.?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(rf"\b[«\"]?{name}[»\"]?\s+explique\s+que\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(rf"\b[«\"]?{name}[»\"]?\s+a\s+pu\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(rf"\b[«\"]?{name}[»\"]?\s+avec\s+", "", text, flags=re.IGNORECASE)
        text = re.sub(rf"[«\"]{name}[»\"]\s*", "", text, flags=re.IGNORECASE)
    if preserve_newlines:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    return re.sub(r"\s+", " ", text).strip()


def _remove_meta_fillers(text: str) -> str:
    fillers = (
        r"Dit simplement\s*:\s*il y a une situation à comprendre, des personnes concernées, et souvent des adultes qui cherchent des décisions ou des solutions\.?",
        r"On n'a pas besoin d'avoir peur pour apprendre ce qui se passe\.?",
        r"À ce stade, l'important est de séparer les faits confirmés, les réponses déjà engagées et les points qui demandent encore vérification\.?",
        r"Le signal mérite attention\s*:\s*les effets peuvent toucher la sécurité, la santé, l'économie ou la confiance publique, et les prochains développements seront déterminants\.?",
        r"L'enjeu, maintenant, c'est de voir qui est touché, ce qui change concrètement et ce qui devra être confirmé dans les prochaines heures\.?",
        r"C'est une information culturelle\s*:\s*elle parle d'artistes, de films, de chansons ou de spectacles\.?",
        r"Ces événements permettent aussi de discuter de la société, des émotions et des histoires que l'on choisit de raconter\.?",
        r"Cette information concerne des décisions prises par des responsables politiques\.?",
        r"Ces décisions peuvent changer l'organisation d'un pays, les règles publiques ou les relations avec d'autres pays\.?",
    )
    for filler in fillers:
        text = re.sub(filler, "", text, flags=re.IGNORECASE)
    return re.sub(r"[ \t]+", " ", text).strip()


def _format_body_paragraphs(text: str) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    if len(paragraphs) > 1:
        return "\n\n".join(paragraphs)
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) <= 3:
        return text.strip()
    grouped = []
    for index in range(0, len(sentences), 2):
        grouped.append(" ".join(sentences[index : index + 2]).strip())
    return "\n\n".join(part for part in grouped if part)


def _source_aliases(source: str) -> list[str]:
    aliases = [source]
    short = source.split(" - ", 1)[0].strip()
    if short and short not in aliases:
        aliases.append(short)
    if short == "TV5Monde":
        aliases.append("TV5")
    return aliases


def _lower_initial_for_flow(text: str) -> str:
    if not text:
        return text
    if len(text) > 1 and text[:2].isalpha() and text[:2].isupper():
        return text
    return text[0].lower() + text[1:]


def _upper_initial(text: str) -> str:
    if not text:
        return text
    return text[0].upper() + text[1:]


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    return text if text[-1] in ".!?" else f"{text}."


def _normalize_for_rules(text: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(char for char in text if not unicodedata.combining(char))


def _word_limit(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip(" ,;:") + "."
