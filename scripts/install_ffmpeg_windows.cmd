@echo off
setlocal
cd /d "%~dp0\.."

set FFMPEG_DIR=tools\ffmpeg
set FFMPEG_ZIP=tools\ffmpeg-release-essentials.zip
set FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip

if exist "%FFMPEG_DIR%\bin\ffmpeg.exe" (
  echo ffmpeg deja installe: %FFMPEG_DIR%\bin\ffmpeg.exe
  exit /b 0
)

if not exist tools mkdir tools

if not exist "%FFMPEG_ZIP%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%FFMPEG_URL%' -OutFile '%FFMPEG_ZIP%' -TimeoutSec 300"
  if errorlevel 1 exit /b 1
)

if not exist "%FFMPEG_DIR%" mkdir "%FFMPEG_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%FFMPEG_ZIP%' -DestinationPath '%FFMPEG_DIR%' -Force"
if errorlevel 1 exit /b 1

if not exist "%FFMPEG_DIR%\bin" mkdir "%FFMPEG_DIR%\bin"
for /r "%FFMPEG_DIR%" %%F in (ffmpeg.exe) do copy /y "%%F" "%FFMPEG_DIR%\bin\ffmpeg.exe" >nul
for /r "%FFMPEG_DIR%" %%F in (ffprobe.exe) do copy /y "%%F" "%FFMPEG_DIR%\bin\ffprobe.exe" >nul

"%FFMPEG_DIR%\bin\ffmpeg.exe" -version
