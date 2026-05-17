from pathlib import Path

from cursor_news.autodj import SLOT_PLAN, _style_key_from_bulletin, upload_readme, write_schedule_csv


def test_slot_plan_covers_full_hour():
    assert [minute for minute, _key, _label in SLOT_PLAN] == ["00", "10", "20", "30", "40", "50"]


def test_style_key_from_bulletin_prefers_id():
    assert _style_key_from_bulletin({"id": "20260517T120000-non_anxiogene-abcd", "style_label": ""}) == "non_anxiogene"
    assert _style_key_from_bulletin({"id": "20260517T121000-enfant-abcd", "style_label": ""}) == "enfant"


def test_write_schedule_csv(tmp_path: Path):
    path = tmp_path / "schedule.csv"
    write_schedule_csv(
        path,
        [
            {
                "minute": "00",
                "style": "Journaliste",
                "file": "CursorNews_00_journaliste.mp3",
                "source_bulletin": "id",
                "title": "Cursor News",
            }
        ],
    )
    text = path.read_text(encoding="utf-8")
    assert "minute,style,file,source_bulletin,title" in text
    assert "CursorNews_00_journaliste.mp3" in text


def test_upload_readme_mentions_pc_can_be_off():
    text = upload_readme(Path("CursorNews_1h_loop.mp3"), [Path("CursorNews_00_journaliste.mp3")])
    assert "PC local peut etre eteint" in text
