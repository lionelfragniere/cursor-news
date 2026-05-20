from datetime import datetime

from cursor_news.gcp_publish import (
    build_manifest,
    latest_bulletins_by_style,
    latest_bulletins_by_topic,
    recent_bulletins_by_topic,
)


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
    assert manifest["bulletins_by_topic"][0]["style_key"] == "enfant"
    assert manifest["bulletins_by_style"][0]["style_key"] == "enfant"
    assert manifest["bulletins_by_style"][0]["audio_url"] == "https://example.test/audio/bulletins/child.mp3"


def test_recent_bulletins_by_topic_keeps_only_retention_window():
    history = [
        {
            "id": "recent",
            "slot_start": "2026-05-18T10:00:00+02:00",
            "style_key": "suisse",
            "audio_path": "recent.mp3",
        },
        {
            "id": "old",
            "slot_start": "2026-05-18T07:00:00+02:00",
            "style_key": "international",
            "audio_path": "old.mp3",
        },
    ]

    selected = recent_bulletins_by_topic(
        history,
        retention_hours=2,
        now=datetime.fromisoformat("2026-05-18T10:30:00+02:00"),
    )

    assert [item["id"] for item in selected] == ["recent"]


def test_latest_bulletins_by_topic_keeps_last_unique_even_when_older():
    history = [
        {
            "id": "recent",
            "slot_start": "2026-05-18T10:00:00+02:00",
            "style_key": "suisse",
            "audio_path": "recent.mp3",
        },
        {
            "id": "old",
            "slot_start": "2026-05-18T07:00:00+02:00",
            "style_key": "international",
            "audio_path": "old.mp3",
        },
        {
            "id": "older-suisse",
            "slot_start": "2026-05-18T06:00:00+02:00",
            "style_key": "suisse",
            "audio_path": "older-suisse.mp3",
        },
    ]

    selected = latest_bulletins_by_topic(history, limit=6)

    assert [item["id"] for item in selected] == ["recent", "old"]


def test_latest_bulletins_by_topic_can_ignore_removed_schedule_keys():
    history = [
        {"id": "old-tone", "style_key": "journaliste", "audio_path": "old-tone.mp3"},
        {"id": "topic", "style_key": "suisse", "audio_path": "topic.mp3"},
    ]

    selected = latest_bulletins_by_topic(history, allowed_keys={"suisse", "international"})

    assert [item["id"] for item in selected] == ["topic"]
