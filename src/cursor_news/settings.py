from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

from dotenv import load_dotenv


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    home: Path
    config_dir: Path
    data_dir: Path
    static_dir: Path
    database_path: Path
    audio_dir: Path
    cache_dir: Path
    timezone: str
    host: str
    port: int
    buffer_slots: int
    generate_max_per_tick: int
    max_articles: int
    ingest_interval_minutes: int
    generate_interval_seconds: int
    llm_provider: str
    ollama_base_url: str
    ollama_model: str
    tts_engine: str
    tts_model_name: str
    edge_tts_voice: str
    edge_tts_rate: str
    coqui_model_name: str
    coqui_device: str
    coqui_speaker_wav: str | None
    coqui_speaker: str | None
    ffmpeg_path: str | None
    allow_wav_fallback: bool
    audio_bitrate: str
    audio_channels: int
    audio_sample_rate: int
    infomaniak_dry_run: bool
    infomaniak_api_base: str
    infomaniak_token: str | None
    infomaniak_metadata_url: str | None
    infomaniak_metadata_username: str | None
    infomaniak_metadata_password: str | None
    infomaniak_metadata_template: str
    infomaniak_public_stream_url: str | None
    infomaniak_listener_url: str | None
    infomaniak_stream_host: str | None
    infomaniak_stream_port: int
    infomaniak_stream_mount: str | None
    infomaniak_stream_username: str
    infomaniak_stream_password: str | None
    infomaniak_stream_bitrate: str
    infomaniak_stream_sample_rate: int
    gcp_project_id: str | None
    gcp_bucket: str | None
    gcloud_path: str
    gcp_public_base_url: str | None
    gcp_bulletin_retention_hours: int

    @property
    def sources_path(self) -> Path:
        return self.config_dir / "sources.yml"

    @property
    def schedule_path(self) -> Path:
        return self.config_dir / "schedule.yml"

    def ensure_dirs(self) -> None:
        for path in (self.config_dir, self.data_dir, self.audio_dir, self.cache_dir):
            path.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    root = project_root()
    load_dotenv(root / ".env")

    home_value = os.getenv("CURSOR_NEWS_HOME", ".").strip() or "."
    home = Path(home_value)
    if not home.is_absolute():
        home = (root / home).resolve()

    load_dotenv(home / ".env", override=False)

    config_dir = _resolve_path(home, os.getenv("CURSOR_NEWS_CONFIG_DIR", str(home / "config")))
    data_dir = _resolve_path(home, os.getenv("CURSOR_NEWS_DATA_DIR", str(home / "data")))
    static_dir = _resolve_path(home, os.getenv("CURSOR_NEWS_STATIC_DIR", str(root / "src" / "cursor_news" / "static")))
    database_path = _resolve_path(home, os.getenv("CURSOR_NEWS_DB", str(data_dir / "cursor_news.sqlite3")))
    audio_dir = _resolve_path(home, os.getenv("CURSOR_NEWS_AUDIO_DIR", str(data_dir / "audio")))
    cache_dir = _resolve_path(home, os.getenv("CURSOR_NEWS_CACHE_DIR", str(data_dir / "cache")))

    metadata_url, metadata_username, metadata_password = _infomaniak_metadata_config()

    settings = Settings(
        home=home,
        config_dir=config_dir,
        data_dir=data_dir,
        static_dir=static_dir,
        database_path=database_path,
        audio_dir=audio_dir,
        cache_dir=cache_dir,
        timezone=os.getenv("CURSOR_NEWS_TIMEZONE", "Europe/Zurich"),
        host=os.getenv("CURSOR_NEWS_HOST", "0.0.0.0"),
        port=int(os.getenv("CURSOR_NEWS_PORT", "8000")),
        buffer_slots=max(1, int(os.getenv("CURSOR_NEWS_BUFFER_SLOTS", "2"))),
        generate_max_per_tick=max(1, int(os.getenv("CURSOR_NEWS_GENERATE_MAX_PER_TICK", "1"))),
        max_articles=max(1, int(os.getenv("CURSOR_NEWS_MAX_ARTICLES", "12"))),
        ingest_interval_minutes=max(1, int(os.getenv("CURSOR_NEWS_INGEST_INTERVAL_MINUTES", "5"))),
        generate_interval_seconds=max(10, int(os.getenv("CURSOR_NEWS_GENERATE_INTERVAL_SECONDS", "60"))),
        llm_provider=os.getenv("LLM_PROVIDER", "ollama").lower(),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:14b"),
        tts_engine=os.getenv("TTS_ENGINE", "piper").lower(),
        tts_model_name=os.getenv("TTS_MODEL_NAME") or os.getenv("COQUI_MODEL_NAME", "models/piper/fr_FR-siwis-medium/fr_FR-siwis-medium.onnx"),
        edge_tts_voice=os.getenv("EDGE_TTS_VOICE", "fr-CH-ArianeNeural"),
        edge_tts_rate=os.getenv("EDGE_TTS_RATE", "-5%"),
        coqui_model_name=os.getenv("COQUI_MODEL_NAME", "tts_models/fr/css10/vits"),
        coqui_device=os.getenv("COQUI_DEVICE", "cpu"),
        coqui_speaker_wav=os.getenv("COQUI_SPEAKER_WAV") or None,
        coqui_speaker=os.getenv("COQUI_SPEAKER") or None,
        ffmpeg_path=_resolve_optional_path(home, os.getenv("FFMPEG_PATH")),
        allow_wav_fallback=_as_bool(os.getenv("ALLOW_WAV_FALLBACK"), False),
        audio_bitrate=os.getenv("AUDIO_BITRATE", "64k"),
        audio_channels=max(1, int(os.getenv("AUDIO_CHANNELS", "1"))),
        audio_sample_rate=max(8000, int(os.getenv("AUDIO_SAMPLE_RATE", "44100"))),
        infomaniak_dry_run=_as_bool(os.getenv("INFOMANIAK_DRY_RUN"), True),
        infomaniak_api_base=os.getenv("INFOMANIAK_API_BASE", "https://api.infomaniak.com").rstrip("/"),
        infomaniak_token=os.getenv("INFOMANIAK_TOKEN") or None,
        infomaniak_metadata_url=metadata_url,
        infomaniak_metadata_username=metadata_username,
        infomaniak_metadata_password=metadata_password,
        infomaniak_metadata_template=os.getenv("INFOMANIAK_METADATA_TEMPLATE", "{artist} - {title}"),
        infomaniak_public_stream_url=(
            os.getenv("INFOMANIAK_PUBLIC_STREAM_URL")
            or os.getenv("INFOMANIAK_LISTENER_URL")
            or os.getenv("INFOMANIAK_HLS_URL")
            or None
        ),
        infomaniak_listener_url=os.getenv("INFOMANIAK_LISTENER_URL") or None,
        infomaniak_stream_host=os.getenv("INFOMANIAK_STREAM_HOST") or None,
        infomaniak_stream_port=int(os.getenv("INFOMANIAK_STREAM_PORT", "80")),
        infomaniak_stream_mount=os.getenv("INFOMANIAK_STREAM_MOUNT") or None,
        infomaniak_stream_username=os.getenv("INFOMANIAK_STREAM_USERNAME", "source"),
        infomaniak_stream_password=os.getenv("INFOMANIAK_STREAM_PASSWORD") or None,
        infomaniak_stream_bitrate=os.getenv("INFOMANIAK_STREAM_BITRATE", "64k"),
        infomaniak_stream_sample_rate=int(os.getenv("INFOMANIAK_STREAM_SAMPLE_RATE", "44100")),
        gcp_project_id=os.getenv("GCP_PROJECT_ID") or None,
        gcp_bucket=os.getenv("GCP_BUCKET") or None,
        gcloud_path=os.getenv("GCLOUD_PATH", "gcloud"),
        gcp_public_base_url=os.getenv("GCP_PUBLIC_BASE_URL") or None,
        gcp_bulletin_retention_hours=max(1, int(os.getenv("GCP_BULLETIN_RETENTION_HOURS", "2"))),
    )

    settings.ensure_dirs()
    return settings


def _resolve_path(home: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (home / path).resolve()


def _resolve_optional_path(home: Path, value: str | None) -> str | None:
    if not value:
        return None
    return str(_resolve_path(home, value))


def _infomaniak_metadata_config() -> tuple[str | None, str | None, str | None]:
    raw_url = os.getenv("INFOMANIAK_METADATA_URL") or None
    username = os.getenv("INFOMANIAK_METADATA_USERNAME") or None
    password = os.getenv("INFOMANIAK_METADATA_PASSWORD") or None
    if not raw_url:
        return None, username, password

    parsed = urlsplit(raw_url)
    if parsed.username and not username:
        username = unquote(parsed.username)
    if parsed.password and not password:
        password = unquote(parsed.password)
    if parsed.username or parsed.password:
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        parsed = parsed._replace(netloc=host)
    return urlunsplit(parsed), username, password
