from cursor_news.article_filter import (
    anxiety_score,
    diversify_articles_by_topic,
    filter_child_unsuitable_articles,
    filter_sports_articles,
    is_child_unsuitable_article,
    is_sports_article,
    rank_articles_for_style,
    story_key,
    unique_articles_by_story,
    unique_articles_by_topic,
)
from cursor_news.models import Article


def article(title: str, summary: str = "") -> Article:
    return Article(
        id=1,
        source_name="Fixture",
        title=title,
        url="https://example.test",
        published_at=None,
        summary=summary,
        content="",
    )


def sourced_article(title: str, source: str, summary: str = "") -> Article:
    return Article(
        id=1,
        source_name=source,
        title=title,
        url=f"https://example.test/{source}",
        published_at=None,
        summary=summary,
        content="",
    )


def test_sports_article_detects_coach_change():
    item = article(
        "Premier League : Xabi Alonso nommé nouvel entraîneur de Chelsea",
        "Le club londonien annonce un changement de coach.",
    )
    assert is_sports_article(item)


def test_sports_article_detects_match_result():
    item = article("Tennis : victoire en finale après un match serré")
    assert is_sports_article(item)


def test_sports_article_detects_documentary_about_footballer():
    item = article('"Je suis une fleur du mal" : Éric Cantona revient sur son passé de footballeur')
    assert is_sports_article(item)


def test_filter_sports_articles_keeps_general_news():
    politics = article("Le Conseil fédéral présente une réforme de la santé")
    football = article("Football : un transfert majeur annoncé")
    assert filter_sports_articles([politics, football]) == [politics]


def test_child_unsuitable_detects_adult_topics():
    item = article("Peut-on avoir une vie sexuelle sous antidépresseurs ?")
    assert is_child_unsuitable_article(item)


def test_child_unsuitable_detects_jihad_or_hard_accident_terms():
    assert is_child_unsuitable_article(article("Retour du jihad : des enfants terrorisés"))
    assert is_child_unsuitable_article(article("Piétons fauchés par une voiture"))


def test_child_unsuitable_detects_humiliation_or_death_topics():
    assert is_child_unsuitable_article(article("Une femme contrainte de se faire raser la tête après une humiliation"))
    assert is_child_unsuitable_article(article("Une cantatrice est morte à l'âge de 79 ans"))


def test_filter_child_unsuitable_articles_keeps_suitable_news():
    suitable = article("Des médecins surveillent une épidémie")
    adult = article("Une enquête ouverte pour violences sexuelles")
    assert filter_child_unsuitable_articles([suitable, adult]) == [suitable]


def test_rank_articles_for_anxiogene_prioritizes_risk():
    calm = article("Festival de Cannes : un film récompensé")
    risk = article("Guerre en Ukraine : nouvelles attaques de drones")
    assert anxiety_score(risk) > anxiety_score(calm)
    assert rank_articles_for_style([calm, risk], "anxiogene") == [risk, calm]


def test_rank_articles_for_non_anxiogene_prioritizes_calm_news():
    risk = article("Guerre en Ukraine : nouvelles attaques de drones")
    calm = article("Festival de Cannes : un film récompensé")
    assert rank_articles_for_style([risk, calm], "non_anxiogene") == [calm, risk]


def test_rank_articles_for_non_anxiogene_drops_high_anxiety_when_enough_calm():
    calm_articles = [article(f"Festival de Cannes : film numéro {index}") for index in range(6)]
    risk = article("Retour du jihad : des enfants terrorisés")
    assert rank_articles_for_style([risk, *calm_articles], "non_anxiogene") == calm_articles


def test_diversify_articles_by_topic_moves_repeated_topics_later():
    eurovision_1 = article("Eurovision : la Bulgarie gagne")
    eurovision_2 = article("Eurovision : la France termine onzième")
    samsung = article("En Corée du Sud, une grève chez Samsung")
    cannes = article("Cannes : un film suisse applaudi")

    assert diversify_articles_by_topic([eurovision_1, eurovision_2, samsung, cannes]) == [
        eurovision_1,
        samsung,
        cannes,
        eurovision_2,
    ]


def test_unique_articles_by_topic_drops_repeated_topics():
    eurovision_1 = article("Eurovision : la Bulgarie gagne")
    eurovision_2 = article("Eurovision : la France termine onzième")
    samsung = article("En Corée du Sud, une grève chez Samsung")

    assert unique_articles_by_topic([eurovision_1, eurovision_2, samsung]) == [eurovision_1, samsung]


def test_unique_articles_by_story_drops_same_title_from_regional_network():
    rtn = sourced_article(
        "Slamer en forêt pour mieux admirer la nature",
        "RTN - Région",
        "La Fête de la nature démarre ce mercredi en Suisse romande.",
    )
    rjb = sourced_article(
        "Slamer en forêt pour mieux admirer la nature",
        "RJB - Région",
        "La Fête de la nature démarre ce mercredi en Suisse romande.",
    )
    other = sourced_article("Un nouveau train est annoncé dans le Jura", "RFJ - Région")

    assert story_key(rtn) == story_key(rjb)
    assert unique_articles_by_story([rtn, rjb, other]) == [rtn, other]
