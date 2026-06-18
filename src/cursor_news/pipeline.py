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
    repair_bulletin_french_accents,
)
from .models import Article, BulletinDraft, StyleSlot
from .schedule import ProgramSchedule
from .settings import Settings
from .tts import build_tts_client


class DraftRejectedError(RuntimeError):
    """Raised when a text draft is not good enough to turn into audio."""


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
                try:
                    bulletin_id = self.generate_slot(slot_start)
                except DraftRejectedError:
                    continue
                if not bulletin_id:
                    continue
                generated.append(bulletin_id)
                if len(generated) >= self.settings.generate_max_per_tick:
                    break
            self.db.finish_run(run_id, "ok", f"{len(generated)} bulletins generated")
            return generated
        except Exception as exc:
            self.db.finish_run(run_id, "error", str(exc))
            raise

    def generate_slot(self, slot_start: datetime) -> str | None:
        self.db.init()
        slot_iso = slot_start.isoformat(timespec="seconds")
        style = self.schedule.style_for(slot_start)
        articles = self._select_articles(style)
        if not articles:
            return None
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

    def draft_slot_text(self, style_key: str, slot_start: datetime | None = None) -> tuple[StyleSlot, list[Article], BulletinDraft]:
        self.db.init()
        style = self._style_by_key(style_key)
        slot_start = slot_start or self.schedule.floor_slot()
        articles = self._select_articles(style)
        if not articles:
            raise DraftRejectedError(f"No usable articles for {style.label}")
        return style, articles, self._draft_bulletin(articles, style, slot_start)

    def _style_by_key(self, style_key: str) -> StyleSlot:
        for style in self.schedule.rotation:
            if style.key == style_key:
                return style
        raise ValueError(f"Unknown style key: {style_key}")

    def _select_articles(self, style: StyleSlot | str | None = None) -> list[Article]:
        style_key, language = self._style_selection_context(style)
        target_articles = min(self.settings.max_articles, 7)
        pool_size = max(target_articles * 5, 30)
        include_english = language == "en"
        if include_english or style_key in {"valais", "suisse_romande", "suisse", "international", "security_world"}:
            pool_size = max(target_articles * 10, 120)
        if style_key == "un_relevant":
            pool_size = max(pool_size, 500)
        selected = filter_sports_articles(self.db.list_candidate_articles(pool_size, include_english=include_english))
        selected = _filter_articles_by_language(selected, language)
        if style_key == "enfant":
            selected = filter_child_unsuitable_articles(selected)
        ranking_style = "non_anxiogene" if style_key == "enfant" else style_key
        selected = filter_articles_for_topic(selected, ranking_style, minimum=max(3, target_articles // 3))
        if len(selected) < target_articles:
            known_ids = {article.id for article in selected}
            recent = filter_sports_articles(self.db.list_recent_articles(pool_size, include_english=include_english))
            recent = _filter_articles_by_language(recent, language)
            if style_key == "enfant":
                recent = filter_child_unsuitable_articles(recent)
            recent = filter_articles_for_topic(recent, ranking_style, minimum=max(3, target_articles // 3))
            recent = [article for article in recent if article.id not in known_ids]
            selected = [*selected, *recent]
        selected = rank_articles_for_topic(selected, ranking_style)
        selected = unique_articles_by_story(selected)
        selected = unique_articles_by_topic(selected) if style_key == "enfant" else diversify_articles_by_topic(selected)
        return selected[:target_articles]

    def _style_selection_context(self, style: StyleSlot | str | None) -> tuple[str | None, str]:
        if isinstance(style, StyleSlot):
            return style.key, style.language
        style_key = style
        if style_key:
            for slot in self.schedule.rotation:
                if slot.key == style_key:
                    return slot.key, slot.language
        return style_key, "fr"

    def _draft_bulletin(self, articles: list[Article], style, slot_start: datetime) -> BulletinDraft:
        if not articles:
            raise DraftRejectedError(f"No usable articles for {style.label}")
        if self.settings.llm_provider == "template":
            client = TemplateLLMClient()
            draft = client.generate_bulletin(articles, style, slot_start)
        elif self.settings.llm_provider == "ollama":
            client = OllamaLLMClient(
                self.settings.ollama_base_url,
                self.settings.ollama_model,
                self.settings.ollama_timeout_seconds,
                self.settings.ollama_json_format,
            )
            draft = self._generate_validated_llm_draft(client, articles, style, slot_start)
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {self.settings.llm_provider}")
        if getattr(style, "language", "fr") == "fr":
            draft = repair_bulletin_french_accents(draft)
        return enforce_source_credit_at_end(draft, articles, language=getattr(style, "language", "fr"))
        try:
            draft = client.generate_bulletin(articles, style, slot_start)
            if not draft.transcript.strip():
                raise ValueError("LLM returned an empty transcript")
            if self.settings.llm_provider != "template":
                issue = _draft_quality_issue(draft)
                if issue and hasattr(client, "revise_bulletin"):
                    draft = client.revise_bulletin(draft, articles, style, slot_start, issue)
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

    def _generate_validated_llm_draft(
        self,
        client: OllamaLLMClient,
        articles: list[Article],
        style: StyleSlot,
        slot_start: datetime,
    ) -> BulletinDraft:
        draft: BulletinDraft | None = None
        issue = ""
        for _attempt in range(3):
            try:
                if draft is None:
                    draft = client.generate_bulletin(articles, style, slot_start)
                else:
                    draft = client.revise_bulletin(draft, articles, style, slot_start, issue)
            except Exception as exc:
                raise DraftRejectedError(f"LLM draft failed for {style.label}: {exc}") from exc

            draft = _normalize_draft_for_quality(draft, articles, style)
            issue = _draft_quality_issue(draft)
            if not issue:
                return draft
        raise DraftRejectedError(f"LLM draft rejected for {style.label}: {issue}")

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
            self._tts_voice_for_style(style),
            self._tts_rate_for_style(style),
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

    def _tts_voice_for_style(self, style) -> str:
        configured_voice = getattr(style, "tts_voice", None)
        if configured_voice:
            return configured_voice
        if getattr(style, "language", "fr") == "en":
            return "en-US-JennyNeural"
        return self.settings.edge_tts_voice

    def _tts_rate_for_style(self, style) -> str:
        if getattr(style, "language", "fr") == "en":
            return "-2%"
        return self.settings.edge_tts_rate

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


def _filter_articles_by_language(articles: list[Article], language: str) -> list[Article]:
    if language == "en":
        return [article for article in articles if article.region == "english" and article.language == "en"]
    return [
        article
        for article in articles
        if article.region != "english" and article.language in {"fr", "unknown"}
    ]


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


def _normalize_draft_for_quality(draft: BulletinDraft, articles: list[Article], style: StyleSlot) -> BulletinDraft:
    language = getattr(style, "language", "fr")
    if language == "fr":
        draft = repair_bulletin_french_accents(draft)
    return enforce_source_credit_at_end(draft, articles, language=language)


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
        "this is a situation to understand",
        "this is cultural news",
        "leaders are making decisions",
        "the key issue now",
        "pays neutre",
        "liens historiques et économiques",
        "impact direct ou indirect sur votre quotidien en suisse romande",
        "influencer notre quotidien",
        "influence notre quotidien",
        "s'indépendir",
        "switzerland, as a neutral country",
        "historical and economic ties",
    )
    if "trop court" in warning_text or "too short" in warning_text:
        return "LLM self-reported a short transcript"
    if transcript.count("sources utilisées pour cette édition") > 1:
        return "LLM returned duplicate source credits"
    if transcript.count("sources used for this edition") > 1:
        return "LLM returned duplicate source credits"
    for phrase in generic_child_phrases:
        if phrase in transcript:
            return f"LLM returned generic radio filler: {phrase}"
    if word_count < 300:
        return f"LLM returned a short transcript ({word_count} words)"
    repeated = _repeated_paragraph_opening(draft.transcript)
    if repeated:
        return f"LLM returned repetitive paragraph openings: {repeated}"
    return None


def _repeated_paragraph_opening(transcript: str) -> str | None:
    paragraphs = [part.strip() for part in transcript.split("\n\n") if len(part.split()) >= 8]
    openings: dict[str, int] = {}
    for paragraph in paragraphs:
        words = [word.strip(" ,;:.!?").lower() for word in paragraph.split()[:3]]
        words = [word for word in words if word]
        if len(words) < 2:
            continue
        opening = " ".join(words)
        openings[opening] = openings.get(opening, 0) + 1
    for opening, count in openings.items():
        if count >= 4:
            return opening
    return None
