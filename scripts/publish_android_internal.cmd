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

if "%ANDROID_PUBLISHER_CREDENTIALS%"=="" if not exist "play-service-account.json" (
  echo Missing Google Play API credentials.
  echo Put the service account JSON at android\play-service-account.json
  echo or set ANDROID_PUBLISHER_CREDENTIALS to the JSON content.
  exit /b 1
)

if not "%~1"=="" set "ANDROID_VERSION_CODE=%~1"
if not "%~2"=="" set "ANDROID_VERSION_NAME=%~2"
if "%PLAY_TRACK%"=="" set "PLAY_TRACK=internal"
if "%PLAY_RELEASE_STATUS%"=="" set "PLAY_RELEASE_STATUS=COMPLETED"

echo Publishing Cursor News to Google Play track: %PLAY_TRACK%
echo Release status: %PLAY_RELEASE_STATUS%
if not "%ANDROID_VERSION_CODE%"=="" echo Version code: %ANDROID_VERSION_CODE%
if not "%ANDROID_VERSION_NAME%"=="" echo Version name: %ANDROID_VERSION_NAME%
echo.

call gradlew.bat :app:publishReleaseBundle :app:publishReleaseListing -PenablePlayPublisher=true --console=plain
