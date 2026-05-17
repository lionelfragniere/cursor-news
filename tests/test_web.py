from pathlib import Path

from fastapi.testclient import TestClient

from cursor_news.settings import load_settings
from cursor_news.web import create_app


def test_status_endpoint(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    settings = load_settings()
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/api/status")
    assert response.status_code == 200
    assert "articles" in response.json()
    assert "archive" in response.json()


def test_history_endpoint_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    settings = load_settings()
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/api/history")
    assert response.status_code == 200
    assert response.json() == []


def test_articles_endpoint_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    settings = load_settings()
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/api/articles")
    assert response.status_code == 200
    assert response.json() == []


def test_stream_endpoint_returns_configured_hls_url(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    monkeypatch.setenv("INFOMANIAK_PUBLIC_STREAM_URL", "https://radio.example.test/live/manifest.m3u8")
    settings = load_settings()
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/api/stream")
    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "url": "https://radio.example.test/live/manifest.m3u8",
        "type": "hls",
        "label": "Direct Infomaniak",
    }


def test_missing_bulletin_endpoint_returns_404(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CURSOR_NEWS_HOME", str(tmp_path))
    monkeypatch.setenv("CURSOR_NEWS_CONFIG_DIR", str(Path.cwd() / "config"))
    monkeypatch.setenv("CURSOR_NEWS_STATIC_DIR", str(Path.cwd() / "src" / "cursor_news" / "static"))
    settings = load_settings()
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/api/bulletins/not-found")
    assert response.status_code == 404
