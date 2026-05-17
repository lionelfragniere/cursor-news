@echo off
setlocal

set "ISO_URL=https://releases.ubuntu.com/26.04/ubuntu-26.04-desktop-amd64.iso"
set "SUMS_URL=https://releases.ubuntu.com/26.04/SHA256SUMS"
set "OUT_DIR=%USERPROFILE%\Downloads\cursor-news-ubuntu-usb"
set "ISO_PATH=%OUT_DIR%\ubuntu-26.04-desktop-amd64.iso"
set "SUMS_PATH=%OUT_DIR%\SHA256SUMS"

if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

echo Cursor News - preparation USB Ubuntu Desktop
echo.
echo Ce script telecharge l'image ISO officielle. Il ne modifie aucun disque USB.
echo Dossier: %OUT_DIR%
echo.

if not exist "%ISO_PATH%" (
  echo Telechargement ISO Ubuntu 26.04 LTS...
  curl.exe -L --fail --output "%ISO_PATH%" "%ISO_URL%"
) else (
  echo ISO deja present: %ISO_PATH%
)

curl.exe -L --fail --output "%SUMS_PATH%" "%SUMS_URL%"

echo.
echo Hash local:
certutil -hashfile "%ISO_PATH%" SHA256
echo.
echo Hash officiel attendu pour ubuntu-26.04-desktop-amd64.iso:
findstr /I "ubuntu-26.04-desktop-amd64.iso" "%SUMS_PATH%"
echo.
echo Prochaine etape:
echo 1. Ouvre Rufus ou BalenaEtcher.
echo 2. Selectionne l'ISO ci-dessus.
echo 3. Choisis la cle USB cible avec attention.
echo 4. Redemarre le laptop et choisis la cle USB dans le menu de boot.
echo.
echo Pages utiles ouvertes dans le navigateur.
start "" "https://ubuntu.com/download/desktop"
start "" "https://rufus.ie/"
start "" "%OUT_DIR%"

endlocal
