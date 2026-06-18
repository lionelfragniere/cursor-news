from datetime import datetime

from cursor_news.llm import (
    OllamaLLMClient,
    TemplateLLMClient,
    build_prompt,
    enforce_source_credit_at_end,
    parse_json_object,
    repair_french_accents,
)
from cursor_news.models import Article, BulletinDraft, StyleSlot


def test_parse_json_object_from_fenced_response():
    parsed = parse_json_object('```json\n{"title":"A","summary":"B","transcript":"C","warnings":[]}\n```')
    assert parsed["title"] == "A"


def test_build_prompt_requires_radio_script_not_rss_reading():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Le Valais annonce une nouvelle mesure",
        url="https://example.test",
        published_at=None,
        summary="Le canton presente une mesure pour les communes.",
        content="",
    )
    prompt = build_prompt([article], StyleSlot(key="valais", label="Valais", prompt="Local"), datetime.now())
    assert prompt.startswith("/no_think")
    assert "Ne pas réciter les titres RSS" in prompt
    assert "Choisir 6 à 9 sujets maximum" in prompt
    assert "Sources utilisées pour cette édition" in prompt


def test_build_prompt_english_keeps_un_briefing_in_english():
    article = Article(
        id=1,
        source_name="UN News",
        title="UN agencies call for humanitarian access",
        url="https://example.test",
        published_at=None,
        summary="UN agencies say aid teams need safer access.",
        content="",
        region="english",
        language="en",
    )
    prompt = build_prompt([article], StyleSlot(key="un_relevant", label="UN / ONU", prompt="UN focus", language="en"), datetime.now())
    assert prompt.startswith("/no_think")
    assert "Keep the briefing in English" in prompt
    assert "Do not read RSS headlines" in prompt
    assert "Sources used for this edition" in prompt


def test_ollama_client_disables_thinking_in_api_payload(monkeypatch):
    captured: list[dict] = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": '{"title":"T","summary":"S","transcript":"Transcript long enough for parsing.","warnings":[]}'}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def post(self, url, json):
            captured.append(json)
            return FakeResponse()

    monkeypatch.setattr("cursor_news.llm.httpx.Client", FakeClient)
    article = Article(
        id=1,
        source_name="Fixture",
        title="A local update",
        url="https://example.test",
        published_at=None,
        summary="A short update.",
        content="",
    )
    client = OllamaLLMClient("http://ollama.test", "qwen3:14b")

    client.generate_bulletin([article], StyleSlot(key="suisse", label="Suisse", prompt=""), datetime.now())

    assert captured
    assert captured[0]["think"] is False
    assert captured[0]["format"] == "json"


def test_template_llm_generates_transcript():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Nouveau titre",
        url="https://example.test",
        published_at=None,
        summary="Un resume court.",
        content="",
    )
    style = StyleSlot(key="flash", label="Flash", prompt="Court")
    draft = TemplateLLMClient().generate_bulletin([article], style, datetime.now())
    assert "Nouveau titre" in draft.transcript
    assert "Sources utilisées pour cette édition: Fixture." in draft.transcript
    assert "Chez Fixture" not in draft.transcript
    assert "Selon Fixture" not in draft.transcript
    assert "Source: Fixture" not in draft.transcript


def test_template_llm_keeps_french_accents():
    article = Article(
        id=1,
        source_name="RFI - Français",
        title="RDC: l'épidémie d'Ebola est une urgence régionale",
        url="https://example.test",
        published_at=None,
        summary="La sécurité sanitaire mérite attention.",
        content="",
    )
    style = StyleSlot(key="anxiogene", label="Anxiogène", prompt="Urgent")
    draft = TemplateLLMClient().generate_bulletin([article], style, datetime.now())
    assert "Édition spéciale" in draft.transcript
    assert "mérite attention" in draft.transcript
    assert "sécurité" in draft.transcript


def test_template_llm_child_tone_stays_radio_fluent():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Une grande décision est annoncée",
        url="https://example.test",
        published_at=None,
        summary="Les responsables expliquent les prochaines étapes.",
        content="",
    )
    style = StyleSlot(key="enfant", label="Pour enfant", prompt="Simple")
    draft = TemplateLLMClient().generate_bulletin([article], style, datetime.now())
    assert "On n'a pas besoin d'avoir peur" not in draft.transcript
    assert "Dit simplement" not in draft.transcript
    assert "situation à comprendre" not in draft.transcript
    assert "prochaines étapes" not in draft.transcript
    assert "des responsables politiques prennent des décisions" not in draft.transcript
    assert "Cette information concerne des décisions prises" not in draft.transcript


def test_template_llm_removes_source_mentions_from_rss_summary_body():
    article = Article(
        id=1,
        source_name="Libération - Tous les articles",
        title="Un reportage au CHU de Nice",
        url="https://example.test",
        published_at=None,
        summary="«Libération» a pu visiter un service spécialisé qui soigne certains patients avec de l'oxygène.",
        content="",
    )
    style = StyleSlot(key="journaliste", label="Journaliste", prompt="Factuel")
    draft = TemplateLLMClient().generate_bulletin([article], style, datetime.now())
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "Libération" not in body
    assert draft.transcript.endswith("Sources utilisées pour cette édition: Libération - Tous les articles.")


def test_template_llm_pote_tone_flows_after_en_clair():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Un changement annoncé",
        url="https://example.test",
        published_at=None,
        summary="Le nouveau dispositif doit être présenté lundi.",
        content="",
    )
    style = StyleSlot(key="pote", label="Pote", prompt="Conversationnel")
    draft = TemplateLLMClient().generate_bulletin([article], style, datetime.now())
    assert "En clair, le nouveau dispositif" in draft.transcript
    assert "L'enjeu, maintenant" not in draft.transcript


def test_template_llm_pote_tone_l_apostrophe_flows_after_en_clair():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Un changement annoncé",
        url="https://example.test",
        published_at=None,
        summary="L'ancien dispositif reste en place jusqu'à lundi.",
        content="",
    )
    style = StyleSlot(key="pote", label="Pote", prompt="Conversationnel")
    draft = TemplateLLMClient().generate_bulletin([article], style, datetime.now())
    assert "En clair, l'ancien dispositif" in draft.transcript


def test_template_llm_no_repeated_meta_fillers():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Un changement annoncé",
        url="https://example.test",
        published_at=None,
        summary="Le dispositif doit être présenté lundi.",
        content="",
    )
    for key, label in [
        ("pote", "Pote"),
        ("non_anxiogene", "Non anxiogène"),
        ("anxiogene", "Anxiogène"),
        ("enfant", "Pour enfant"),
        ("journaliste", "Journaliste"),
    ]:
        draft = TemplateLLMClient().generate_bulletin([article], StyleSlot(key=key, label=label, prompt=""), datetime.now())
        assert "il y a une situation à comprendre" not in draft.transcript
        assert "À ce stade, l'important" not in draft.transcript
        assert "Le signal mérite attention" not in draft.transcript
        assert "L'enjeu, maintenant" not in draft.transcript


def test_repair_french_accents_common_radio_terms():
    text = repair_french_accents(
        "Edition speciale: les consequences touchent la securite, la sante et l'economie. "
        "Le signal merite attention des que la redaction verifiera les elements."
    )
    assert "Édition spéciale" in text
    assert "conséquences" in text
    assert "sécurité" in text
    assert "santé" in text
    assert "économie" in text
    assert "mérite attention" in text
    assert "dès que" in text
    assert "rédaction" in text
    assert "vérifiera" in text
    assert "éléments" in text


def test_enforce_source_credit_at_end_removes_inline_sources():
    article = Article(
        id=1,
        source_name="RFI - Français",
        title="Un titre",
        url="https://example.test",
        published_at=None,
        summary="",
        content="",
    )
    draft = enforce_source_credit_at_end(
        draft=TemplateLLMClient().generate_bulletin([article], StyleSlot(key="flash", label="Flash", prompt=""), datetime.now()),
        articles=[article],
    )
    assert draft.transcript.endswith("Sources utilisées pour cette édition: RFI - Français.")
    assert draft.transcript.count("Sources utilisées pour cette édition:") == 1
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "Selon RFI - Français" not in body
    assert "Source: RFI - Français" not in body


def test_enforce_source_credit_formats_long_single_block_and_removes_fillers():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Un titre",
        url="https://example.test",
        published_at=None,
        summary="",
        content="",
    )
    draft = enforce_source_credit_at_end(
        draft=BulletinDraft(
            title="Test",
            summary="",
            transcript=(
                "Introduction courte. Première information importante. "
                "Dit simplement: il y a une situation à comprendre, des personnes concernées, et souvent des adultes qui cherchent des décisions ou des solutions. "
                "Deuxième information importante. Troisième information importante. Conclusion courte."
            ),
        ),
        articles=[article],
    )
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "situation à comprendre" not in body
    assert "\n\n" in body


def test_enforce_source_credit_preserves_existing_paragraphs():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Un titre",
        url="https://example.test",
        published_at=None,
        summary="",
        content="",
    )
    draft = enforce_source_credit_at_end(
        draft=BulletinDraft(
            title="Test",
            summary="",
            transcript="Intro.\n\nD'abord, une information.\n\nAutre dossier important, une autre information.",
        ),
        articles=[article],
    )
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "Intro.\n\nD'abord" in body
    assert "information.\n\nAutre dossier" in body


def test_template_llm_removes_article_bylines():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Un titre",
        url="https://example.test",
        published_at=None,
        summary="Par Elena Lionnet avec Associated Press À deux reprises cette semaine, un responsable a présenté son projet.",
        content="",
    )
    draft = TemplateLLMClient().generate_bulletin([article], StyleSlot(key="journaliste", label="Journaliste", prompt=""), datetime.now())
    assert "Par Elena" not in draft.transcript
    assert "À deux reprises" in draft.transcript


def test_template_llm_removes_tv5_wire_artifacts():
    article = Article(
        id=1,
        source_name="TV5Monde - Information",
        title="Un sommet diplomatique",
        url="https://example.test",
        published_at=None,
        summary=(
            "Fontana avec agences Par Lorène Bienvenu avec agences TV5 JWPlayer Field "
            "Donald Trump se rend en Chine pour rencontrer Xi Jinping."
        ),
        content="",
    )
    draft = TemplateLLMClient().generate_bulletin([article], StyleSlot(key="journaliste", label="Journaliste", prompt=""), datetime.now())
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "Fontana avec agences" not in body
    assert "Par Lorène" not in body
    assert "TV5 JWPlayer Field" not in body
    assert "Donald Trump se rend en Chine" in body


def test_template_llm_child_adapts_war_content_for_children():
    article = Article(
        id=1,
        source_name="Fixture",
        title="EN DIRECT, guerre en Ukraine : la Russie affirme avoir abattu plus de 500 drones ; au moins quatre morts",
        url="https://example.test",
        published_at=None,
        summary="Des bombardements ont frappé plusieurs villes, avec des morts et des blessés.",
        content="",
    )
    draft = TemplateLLMClient().generate_bulletin([article], StyleSlot(key="enfant", label="Pour enfant", prompt=""), datetime.now())
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "EN DIRECT" not in body
    assert "500 drones" not in body
    assert "quatre morts" not in body
    assert "bombardements" not in body
    assert "en Ukraine, la guerre continue" in body
    assert "familles cherchent surtout à rester en sécurité" in body


def test_template_llm_child_adapts_health_content_for_children():
    article = Article(
        id=1,
        source_name="Fixture",
        title="L'OMS déclare une urgence internationale pour l'épidémie d'Ebola",
        url="https://example.test",
        published_at=None,
        summary="Le virus est surveillé par les autorités sanitaires.",
        content="",
    )
    draft = TemplateLLMClient().generate_bulletin([article], StyleSlot(key="enfant", label="Pour enfant", prompt=""), datetime.now())
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "des médecins surveillent l'épidémie d'Ebola" in body
    assert "virus est surveillé" in body


def test_template_llm_child_adapts_hantavirus_content_for_children():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Hantavirus : une passagère diagnostiquée présumée positive",
        url="https://example.test",
        published_at=None,
        summary="Des passagers se trouvaient à bord d'un navire touché par un foyer de hantavirus.",
        content="",
    )
    draft = TemplateLLMClient().generate_bulletin([article], StyleSlot(key="enfant", label="Pour enfant", prompt=""), datetime.now())
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "des médecins surveillent un virus détecté pendant un voyage" in body
    assert "test inquiétant" in body
    assert "foyer de hantavirus" not in body


def test_template_llm_child_uses_title_category_before_body_keywords():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Cannes : un film marque les spectateurs",
        url="https://example.test",
        published_at=None,
        summary="Le film raconte une famille pendant une guerre.",
        content="",
    )
    draft = TemplateLLMClient().generate_bulletin([article], StyleSlot(key="enfant", label="Pour enfant", prompt=""), datetime.now())
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "au Festival de Cannes, de nouveaux films font parler" in body
    assert "information culturelle" not in body
    assert "Dans cette région" not in body


def test_template_llm_child_treats_eurovision_with_israel_as_culture():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Eurovision : Israël arrive deuxième malgré le boycott",
        url="https://example.test",
        published_at=None,
        summary="La soirée musicale a réuni plusieurs pays.",
        content="",
    )
    draft = TemplateLLMClient().generate_bulletin([article], StyleSlot(key="enfant", label="Pour enfant", prompt=""), datetime.now())
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "à l'Eurovision" in body
    assert "Israël arrive aussi en haut du classement" in body
    assert "une nouvelle arrive du monde de la culture" not in body
    assert "la situation reste difficile au Moyen-Orient" not in body


def test_template_llm_child_simplifies_long_eurovision_title():
    article = Article(
        id=1,
        source_name="Fixture",
        title="Première victoire bulgare, Israël arrive deuxième malgré le boycott, la France dégringole... Ce qu'il faut retenir de l'Eurovision 2026",
        url="https://example.test",
        published_at=None,
        summary='La chanteuse bulgare Dara a remporté la 70e édition avec le titre survitaminé "Bangaranga".',
        content="",
    )
    draft = TemplateLLMClient().generate_bulletin([article], StyleSlot(key="enfant", label="Pour enfant", prompt=""), datetime.now())
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "à l'Eurovision, la Bulgarie gagne pour la première fois" in body
    assert "dégringole" not in body
    assert "survitaminé" not in body


def test_template_llm_child_adapts_workplace_topic():
    article = Article(
        id=1,
        source_name="Fixture",
        title="En Corée du Sud, une grève inhabituelle chez Samsung",
        url="https://example.test",
        published_at=None,
        summary="Les salariés du géant coréen demandent de meilleures conditions de travail.",
        content="",
    )
    draft = TemplateLLMClient().generate_bulletin([article], StyleSlot(key="enfant", label="Pour enfant", prompt=""), datetime.now())
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "des employés de Samsung font grève" in body
    assert "conditions de travail" in body
    assert "géant coréen" not in body


def test_template_llm_child_keeps_repeated_culture_items_concrete():
    articles = [
        Article(
            id=1,
            source_name="Fixture",
            title="Cannes : un film suisse marque les spectateurs",
            url="https://example.test/1",
            published_at=None,
            summary="Le film parle d'une famille qui cherche sa place.",
            content="",
        ),
        Article(
            id=2,
            source_name="Fixture",
            title="Eurovision : la Bulgarie gagne pour la première fois",
            url="https://example.test/2",
            published_at=None,
            summary="La chanson de Dara a été remarquée pendant la soirée musicale.",
            content="",
        ),
        Article(
            id=3,
            source_name="Fixture",
            title="Cinéma : un documentaire sur l'école arrive en salles",
            url="https://example.test/3",
            published_at=None,
            summary="Le documentaire suit des élèves et leurs enseignants pendant une année.",
            content="",
        ),
    ]
    draft = TemplateLLMClient().generate_bulletin(articles, StyleSlot(key="enfant", label="Pour enfant", prompt=""), datetime.now())
    body = draft.transcript.rsplit("Sources utilisées pour cette édition:", 1)[0]
    assert "une nouvelle arrive du monde de la culture" not in body
    assert "C'est une information culturelle" not in body
    assert "au Festival de Cannes, de nouveaux films font parler" in body
    assert "à l'Eurovision, la Bulgarie gagne pour la première fois" in body
    assert "documentaire sur l'école" in body
