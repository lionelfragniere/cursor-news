@echo off
setlocal
cd /d "%~dp0\.."
uv run cursor-news stream --limit 12
