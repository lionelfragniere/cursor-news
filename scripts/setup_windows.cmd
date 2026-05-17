@echo off
setlocal
cd /d "%~dp0\.."

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher py.exe introuvable.
  exit /b 1
)

uv venv --python 3.10
if errorlevel 1 exit /b 1

call scripts\install_ffmpeg_windows.cmd
if errorlevel 1 exit /b 1

uv sync --extra dev
if errorlevel 1 exit /b 1

uv pip install --python .venv\Scripts\python.exe "piper-tts>=1.4.2" "onnxruntime>=1.23,<1.24"
if errorlevel 1 exit /b 1

uv pip install --python .venv\Scripts\python.exe "torch>=2.2,<2.9" "torchaudio>=2.2,<2.9" --torch-backend=cpu
if errorlevel 1 exit /b 1

uv pip install --python .venv\Scripts\python.exe "coqui-tts[languages]>=0.27.5" "transformers>=4.41,<5"
if errorlevel 1 exit /b 1

echo.
echo Setup termine.
echo Voix Coqui CPU installee.
if not exist .env copy .env.example .env >nul
echo .env pret. Ajustez les sources et le modele si necessaire.
