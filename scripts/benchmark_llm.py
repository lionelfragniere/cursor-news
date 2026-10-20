"""Compare local models on a frozen source pack, without publishing audio."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from cursor_news.llm import OllamaLLMClient
from cursor_news.models import Article, StyleSlot
from cursor_news.pipeline import _draft_quality_issue, _normalize_draft_for_quality
from cursor_news.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True, help="JSON with articles, style and slot_start")
    parser.add_argument("--model", required=True)
    parser.add_argument("--threads", type=int, help="Default: configured OLLAMA_NUM_THREADS")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revise", action="store_true", help="Allow one revision if the quality check fails")
    args = parser.parse_args()
    settings = load_settings()
    threads = args.threads if args.threads is not None else settings.ollama_num_threads
    if threads < 1:
        parser.error("--threads must be positive")
    pack = json.loads(args.pack.read_text(encoding="utf-8"))
    articles = [Article(**item) for item in pack["articles"]]
    style = StyleSlot(**pack["style"])
    slot = datetime.fromisoformat(pack["slot_start"])
    client = OllamaLLMClient(
        settings.ollama_base_url, args.model, settings.ollama_timeout_seconds,
        settings.ollama_json_format, threads,
    )
    report = {
        "model": args.model,
        "threads": threads,
        "pack": str(args.pack),
        "slot_start": pack["slot_start"],
        "attempts": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    draft = None
    issue = None
    for _ in range(2 if args.revise else 1):
        started = time.monotonic()
        try:
            draft = (
                client.generate_bulletin(articles, style, slot) if draft is None
                else client.revise_bulletin(draft, articles, style, slot, issue or "")
            )
            raw_draft = asdict(draft)
            draft = _normalize_draft_for_quality(draft, articles, style)
            issue = _draft_quality_issue(draft, style)
            result = {
                "raw_draft": raw_draft, "draft": asdict(draft),
                "words": len(draft.transcript.split()), "quality_issue": issue,
            }
        except Exception as exc:
            result = {"error": str(exc)}
            issue = str(exc)
        result["seconds"] = round(time.monotonic() - started, 2)
        report["attempts"].append(result)
        report["total_seconds"] = round(sum(item["seconds"] for item in report["attempts"]), 2)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: value for key, value in result.items() if key not in {"draft", "raw_draft"}}), flush=True)
        if not issue or "error" in result:
            break
    print(f"Report: {args.output}", flush=True)
    return 1 if issue else 0


if __name__ == "__main__":
    raise SystemExit(main())
