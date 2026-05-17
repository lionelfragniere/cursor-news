@echo off
setlocal
cd /d "%~dp0\.."
uv run cursor-news ingest --once
uv run cursor-news generate --slot buffer
