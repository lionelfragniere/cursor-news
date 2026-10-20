import json
import runpy
import sys
from dataclasses import asdict
from pathlib import Path

from cursor_news.models import BulletinDraft, StyleSlot


def test_benchmark_records_first_draft_and_revision_without_publishing(tmp_path, monkeypatch):
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({
        "articles": [],
        "style": asdict(StyleSlot("flash_horaire", "Suisse et monde", "Factuel")),
        "slot_start": "2026-10-20T14:00:00+02:00",
    }), encoding="utf-8")
    output = tmp_path / "report.json"

    class FakeLLM:
        def __init__(self, *args):
            assert args[1] == "small:test"
            assert args[-1] == 2

        def generate_bulletin(self, *args):
            return BulletinDraft("Titre", "Résumé", "Un texte court.")

        def revise_bulletin(self, draft, articles, style, slot, issue):
            assert "short transcript" in issue
            return BulletinDraft("Titre", "Résumé", " ".join(["actualité"] * 350))

    monkeypatch.setattr("cursor_news.llm.OllamaLLMClient", FakeLLM)
    monkeypatch.setattr(sys, "argv", [
        "benchmark_llm.py", "--pack", str(pack), "--model", "small:test",
        "--threads", "2", "--output", str(output), "--revise",
    ])
    script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_llm.py"
    benchmark = runpy.run_path(str(script))

    assert benchmark["main"]() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(report["attempts"]) == 2
    assert "short transcript" in report["attempts"][0]["quality_issue"]
    assert report["attempts"][1]["quality_issue"] is None
    assert report["attempts"][1]["words"] == 350
    assert report["total_seconds"] >= 0


def test_benchmark_preserves_request_errors_in_report(tmp_path, monkeypatch):
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({
        "articles": [], "style": asdict(StyleSlot("flash_horaire", "Flash", "")),
        "slot_start": "2026-10-20T14:00:00+02:00",
    }), encoding="utf-8")
    output = tmp_path / "report.json"

    class UnavailableLLM:
        def __init__(self, *args):
            pass

        def generate_bulletin(self, *args):
            raise RuntimeError("Model unavailable")

    monkeypatch.setattr("cursor_news.llm.OllamaLLMClient", UnavailableLLM)
    monkeypatch.setattr(sys, "argv", [
        "benchmark_llm.py", "--pack", str(pack), "--model", "missing",
        "--output", str(output), "--revise",
    ])
    script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_llm.py"
    benchmark = runpy.run_path(str(script))
    assert benchmark["main"]() == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(report["attempts"]) == 1
    assert report["attempts"][0]["error"] == "Model unavailable"
