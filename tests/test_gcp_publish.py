from cursor_news.gcp_publish import build_manifest, latest_bulletins_by_style


def test_latest_bulletins_by_style_keeps_one_per_tone():
    history = [
        {"id": "a", "style_key": "journaliste", "audio_path": "a.mp3"},
        {"id": "b", "style_key": "journaliste", "audio_path": "b.mp3"},
        {"id": "c", "style_key": "pote", "audio_path": "c.mp3"},
        {"id": "d", "style_key": "enfant", "audio_path": ""},
        {"id": "e", "style_key": "anxiogene", "audio_path": "e.mp3"},
    ]

    selected = latest_bulletins_by_style(history)

    assert [item["id"] for item in selected] == ["a", "c", "e"]


def test_manifest_includes_current_and_bulletins_by_style():
    current = {
        "id": "current",
        "slot_start": "2026-05-18T10:00:00+02:00",
        "style_key": "journaliste",
        "style_label": "Journaliste",
        "title": "Cursor News - Journaliste",
    }
    child = {
        "id": "child",
        "slot_start": "2026-05-18T10:40:00+02:00",
        "style_key": "enfant",
        "style_label": "Pour enfant",
        "title": "Cursor News - Pour enfant",
    }

    manifest = build_manifest(current, "https://example.test/audio", [child])

    assert manifest["current"]["audio_url"] == "https://example.test/audio/current/live.mp3"
    assert manifest["current"]["archive_audio_url"] == "https://example.test/audio/bulletins/current.mp3"
    assert manifest["bulletins_by_style"][0]["style_key"] == "enfant"
    assert manifest["bulletins_by_style"][0]["audio_url"] == "https://example.test/audio/bulletins/child.mp3"
