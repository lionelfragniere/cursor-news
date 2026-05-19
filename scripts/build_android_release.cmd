@echo off
setlocal

cd /d "%~dp0..\android"

set "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"
set "ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk"
set "ANDROID_SDK_ROOT=%ANDROID_HOME%"
set "PATH=%JAVA_HOME%\bin;%ANDROID_HOME%\platform-tools;%PATH%"

if not exist "release.properties" (
  echo Missing android\release.properties.
  echo Run scripts\create_android_upload_key.cmd first, or create release.properties from android\release.properties.example.
  exit /b 1
)

call gradlew.bat :app:bundleRelease --console=plain
if errorlevel 1 exit /b 1

echo.
echo Release bundle ready:
echo   %CD%\app\build\outputs\bundle\release\app-release.aab
