@echo off
setlocal

cd /d "%~dp0.."

set "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"
set "PATH=%JAVA_HOME%\bin;%PATH%"

set "KEYSTORE_DIR=android\keystores"
set "KEYSTORE_FILE=%KEYSTORE_DIR%\cursor-news-upload.jks"
set "KEY_ALIAS=cursor-news-upload"

if not exist "%KEYSTORE_DIR%" mkdir "%KEYSTORE_DIR%"

if exist "%KEYSTORE_FILE%" (
  echo Upload key already exists: %KEYSTORE_FILE%
  echo Nothing changed.
  exit /b 0
)

echo This creates the local Google Play upload key.
echo Keep android\keystores\ and android\release.properties private and backed up.
echo.

set /p STORE_PASSWORD=Keystore password:
set /p KEY_PASSWORD=Key password ^(Enter to reuse keystore password^):
if "%KEY_PASSWORD%"=="" set "KEY_PASSWORD=%STORE_PASSWORD%"

keytool -genkeypair ^
  -v ^
  -storetype JKS ^
  -keystore "%KEYSTORE_FILE%" ^
  -alias "%KEY_ALIAS%" ^
  -keyalg RSA ^
  -keysize 4096 ^
  -validity 10000 ^
  -dname "CN=Lionel Fragniere, OU=Cursor News, O=Cursor News, L=Fribourg, ST=Fribourg, C=CH" ^
  -storepass "%STORE_PASSWORD%" ^
  -keypass "%KEY_PASSWORD%"

if errorlevel 1 exit /b 1

(
  echo storeFile=keystores/cursor-news-upload.jks
  echo storePassword=%STORE_PASSWORD%
  echo keyAlias=%KEY_ALIAS%
  echo keyPassword=%KEY_PASSWORD%
) > android\release.properties

echo.
echo Created:
echo   %KEYSTORE_FILE%
echo   android\release.properties
echo.
echo Back up both files somewhere private. They are ignored by Git.
