from cursor_news.language import detect_article_language, normalize_article_language


def test_detect_article_language_french():
    language = detect_article_language(
        "Le Conseil d'Etat présente une nouvelle mesure",
        "Le gouvernement explique son projet pour les communes et les familles.",
        source_region="valais",
    )

    assert language == "fr"


def test_detect_article_language_german():
    language = detect_article_language(
        "Der Staatsrat informiert über neue Massnahmen",
        "Die Regierung im Wallis stellt eine neue Regelung für die Gemeinden vor.",
        source_region="valais",
    )

    assert language == "de"


def test_english_region_forces_english_language():
    assert detect_article_language("ONU alert", "Texte court", source_region="english") == "en"


def test_normalize_article_language_aliases():
    assert normalize_article_language("de-CH") == "de"
    assert normalize_article_language("fr-FR") == "fr"
    assert normalize_article_language("something") == "unknown"
