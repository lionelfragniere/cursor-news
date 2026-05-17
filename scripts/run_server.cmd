@echo off
setlocal
cd /d "%~dp0\.."
if "%CURSOR_NEWS_HOST%"=="" set CURSOR_NEWS_HOST=0.0.0.0
if "%CURSOR_NEWS_PORT%"=="" set CURSOR_NEWS_PORT=8000
uv run cursor-news serve --host %CURSOR_NEWS_HOST% --port %CURSOR_NEWS_PORT%
