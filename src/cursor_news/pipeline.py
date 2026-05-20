from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from .article_filter import (
    diversify_articles_by_topic,
    filter_articles_for_topic,
    filter_child_unsuitable_articles,
    filter_sports_articles,
    rank_articles_for_topic,
    unique_articles_by_story,
    unique_articles_by_topic,
)
from .audio import AudioEncoder
from .database import Database
from .ingest import FeedIngestor
from .llm import (
    OllamaLLMClient,
    TemplateLLMClient,
    enforce_source_credit_at_end,
    fallback_bulletin,
    repair_bulletin_french_accents,
)
from .models import Article, BulletinDraft
from .schedule import ProgramSchedule
from .settings import Settings
from .tts import build_tts_client


class CursorNewsPipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.database_path)
        self.schedule = ProgramSchedule.load(settings.schedule_path)

    def init_db(self) -> None:
        self.db.init()

    def ingest_once(self) -> dict:
        self.db.init()
        run_id = self.db.start_run("ingest")
        try:
            result = FeedIngestor(self.db, self.settings.sources_path).ingest_all()
            self.db.finish_run(run_id, "ok", f"{result['new_articles']} new articles")
            return result
        except Exception as exc:
            self.db.finish_run(run_id, "error", str(exc))
            raise

    def generate_buffer(self, now: datetime | None = None) -> list[str]:
        self.db.init()
        run_id = self.db.start_run("generate")
        generated: list[str] = []
        try:
            for slot_start in self.schedule.upcoming_slots(self.settings.buffer_slots, now=now):
                slot_iso = slot_start.isoformat(timespec="seconds")
                if self.db.bulletin_exists(slot_iso):
                    continue
                generated.append(self.generate_slot(slot_start))
                if len(generated) >= self.settings.generate_max_per_tick:
                    break
            self.db.finish_run(run_id, "ok", f"{len(generated)} bulletins generated")
            return generated
        except Exception as exc:
            self.db.finish_run(run_id, "error", str(exc))
            raise

    def generate_slot(self, slot_start: datetime) -> str:
        self.db.init()
        slot_iso = slot_start.isoformat(timespec="seconds")
        style = self.schedule.style_for(slot_start)
        articles = self._select_articles(style.key)
        draft = self._draft_bulletin(articles, style, slot_start)
        bulletin_id = f"{slot_start.strftime('%Y%m%dT%H%M%S')}-{style.key}-{uuid.uuid4().hex[:8]}"
        self.db.create_bulletin(bulletin_id, slot_iso, style, draft, articles)
        try:
            audio = self._render_audio(bulletin_id, draft, style)
            self.db.mark_bulletin_ready(bulletin_id, audio)
        except Exception as exc:
            self.db.mark_bulletin_error(bulletin_id, str(exc))
            raise
        return bulletin_id

    def _select_articles(self, style_key: str | None = None) -> list[Article]:
        pool_size = max(self.settings.max_articles * 5, 30)
        include_english = style_key in {"un_relevant", "international_english", "security_world"}
        if include_english or style_key in {"valais", "suisse_romande", "suisse", "international"}:
            pool_size = max(self.settings.max_articles * 10, 120)
        selected = filter_sports_articles(self.db.list_candidate_articles(pool_size, include_english=include_english))
        if style_key == "enfant":
            selected = filter_child_unsuitable_articles(selected)
        ranking_style = "non_anxiogene" if style_key == "enfant" else style_key
        selected = filter_articles_for_topic(selected, ranking_style, minimum=max(3, self.settings.max_articles // 3))
        if len(selected) < self.settings.max_articles:
            known_ids = {article.id for article in selected}
            recent = filter_sports_articles(self.db.list_recent_articles(pool_size, include_english=include_english))
            if style_key == "enfant":
                recent = filter_child_unsuitable_articles(recent)
            recent = filter_articles_for_topic(recent, ranking_style, minimum=max(3, self.settings.max_articles // 3))
            recent = [article for article in recent if article.id not in known_ids]
            selected = [*selected, *recent]
        selected = rank_articles_for_topic(selected, ranking_style)
        selected = unique_articles_by_story(selected)
        selected = unique_articles_by_topic(selected) if style_key == "enfant" else diversify_articles_by_topic(selected)
        return selected[: self.settings.max_articles]

    def _draft_bulletin(self, articles: list[Article], style, slot_start: datetime) -> BulletinDraft:
        if not articles:
            return fallback_bulletin(style)
        if self.settings.llm_provider == "template":
            client = TemplateLLMClient()
        elif self.settings.llm_provider == "ollama":
            client = OllamaLLMClient(
                self.settings.ollama_base_url,
                self.settings.ollama_model,
                self.settings.ollama_timeout_seconds,
            )
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {self.settings.llm_provider}")
        try:
            draft = client.generate_bulletin(articles, style, slot_start)
            if not draft.transcript.strip():
                raise ValueError("LLM returned an empty transcript")
            if self.settings.llm_provider != "template":
                issue = _draft_quality_issue(draft)
                if issue:
                    raise ValueError(issue)
        except Exception as exc:
            draft = TemplateLLMClient().generate_bulletin(articles, style, slot_start)
            draft = BulletinDraft(
                title=draft.title,
                summary=draft.summary,
                transcript=draft.transcript,
                warnings=[*draft.warnings, f"Fallback template après erreur LLM: {exc}"],
            )
        if getattr(style, "language", "fr") == "fr":
            draft = repair_bulletin_french_accents(draft)
        return enforce_source_credit_at_end(draft, articles, language=getattr(style, "language", "fr"))

    def _render_audio(self, bulletin_id: str, draft: BulletinDraft, style):
        stem = _safe_stem(bulletin_id)
        wav_path = self.settings.audio_dir / f"{stem}.wav"
        target_path = self.settings.audio_dir / stem
        tts = build_tts_client(
            self.settings.tts_engine,
            self.settings.tts_model_name,
            self.settings.coqui_device,
            self.settings.coqui_speaker_wav,
            self.settings.coqui_speaker,
            self.settings.home,
            self.settings.ffmpeg_path,
            getattr(style, "tts_voice", None) or self.settings.edge_tts_voice,
            self.settings.edge_tts_rate,
        )
        tts.synthesize_to_wav(draft.transcript, wav_path)
        encoder = AudioEncoder(
            self.settings.ffmpeg_path,
            self.settings.allow_wav_fallback,
            bitrate=self.settings.audio_bitrate,
            channels=self.settings.audio_channels,
            sample_rate=self.settings.audio_sample_rate,
        )
        return encoder.encode_for_web(wav_path, target_path, draft.title)

    def upload_dry_run(self) -> list[str]:
        current = self.db.current_bulletin()
        if not current or not current.get("audio_path"):
            return ["No ready bulletin to upload."]
        from .uploader import DryRunInfomaniakUploader

        result = DryRunInfomaniakUploader().upload(Path(current["audio_path"]), {"title": current["title"]})
        return [result.message]

    def publish_current_metadata(self, dry_run: bool | None = None) -> list[str]:
        current = self.db.current_bulletin()
        if not current:
            return ["No ready bulletin to publish."]
        metadata = _infomaniak_metadata_text(current, self.settings.infomaniak_metadata_template)
        if dry_run is None:
            dry_run = self.settings.infomaniak_dry_run
        if dry_run:
            from .uploader import DryRunInfomaniakMetadataClient

            result = DryRunInfomaniakMetadataClient().update(metadata)
            return [result.message]
        if not self.settings.infomaniak_metadata_url:
            raise ValueError("INFOMANIAK_METADATA_URL is required for metadata publishing")
        from .uploader import InfomaniakMetadataClient

        result = InfomaniakMetadataClient(
            self.settings.infomaniak_metadata_url,
            self.settings.infomaniak_metadata_username,
            self.settings.infomaniak_metadata_password,
        ).update(metadata)
        return [result.message]


def _safe_stem(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value)


def _infomaniak_metadata_text(item: dict, template: str) -> str:
    title = str(item.get("title") or "Cursor News").removeprefix("Cursor News - ").strip()
    values = {
        "artist": "Cursor News",
        "title": title,
        "style": str(item.get("style_label") or title),
        "id": str(item.get("id") or ""),
    }
    try:
        return template.format(**values)
    except Exception:
        return f"{values['artist']} - {values['title']}"


def _draft_quality_issue(draft: BulletinDraft) -> str | None:
    word_count = len(draft.transcript.split())
    warning_text = " ".join(draft.warnings).lower()
    transcript = draft.transcript.lower()
    generic_child_phrases = (
        "une nouvelle arrive du monde de la culture",
        "c'est une information culturelle",
        "des responsables politiques prennent des décisions",
        "cette information concerne des décisions prises",
        "il y a une situation à comprendre",
    )
    if "trop court" in warning_text or "too short" in warning_text:
        return "LLM self-reported a short transcript"
    if word_count < 820:
        return f"LLM returned a short transcript ({word_count} words)"
    for phrase in generic_child_phrases:
        if phrase in transcript:
            return f"LLM returned generic radio filler: {phrase}"
    return None
