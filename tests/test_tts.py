from cursor_news.tts import prepare_online_tts_text, prepare_piper_text, prepare_tts_text


def test_prepare_tts_text_rewrites_digits_and_quotes():
    text = prepare_tts_text("Il y a 24 cas « confirmés » et une 70ᵉ édition aujourd’hui. +27% le 19juillet | matin.")
    assert "vingt-quatre" in text
    assert "soixante-dix" in text
    assert "plus vingt-sept pour cent" in text
    assert "dix-neuf juillet" in text
    assert "«" not in text
    assert "|" not in text
    assert "aujourd'hui" in text


def test_prepare_piper_text_splits_long_bulletins_into_short_lines():
    text = (
        "EN DIRECT, L'OMS observe 246 cas en RDC. "
        "Ceci est une phrase très longue avec beaucoup de détails, des virgules, des précisions, "
        "et encore des informations qui doivent être lues avec des pauses pour rester compréhensibles par la voix locale."
    )
    prepared = prepare_piper_text(text)
    lines = prepared.strip().splitlines()

    assert len(lines) >= 2
    assert max(len(line) for line in lines) <= 180
    assert "EN DIRECT" not in prepared
    assert "Organisation mondiale de la sante" in prepared
    assert "Congo" in prepared
    assert "é" not in prepared


def test_prepare_online_tts_text_preserves_accents():
    prepared = prepare_online_tts_text("Édition spéciale. Les actualités françaises sont vérifiées.")
    assert "Édition spéciale" in prepared
    assert "actualités françaises" in prepared
    assert "vérifiées" in prepared
