# Cursor News Android

Native Android app for Cursor News, including Android Auto media playback.

## Features

- Loads `manifest.json` and `news.json` from the public GCP bucket.
- Displays scraped articles with local search and filters.
- Supports French and English article filters.
- Hides read articles by default.
- Saves read state and filter preferences locally on the device.
- Offers a "Tout lu" action with confirmation.
- Plays the current bulletin and the latest bulletin by topic.
- Android Auto exposes the audio experience as a media app.

## Build Debug APK

Android Studio and the Android SDK must be installed.

```cmd
scripts\build_android_debug.cmd
```

Output:

```text
android\app\build\outputs\apk\debug\app-debug.apk
```

Install on a connected device:

```cmd
%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe install -r android\app\build\outputs\apk\debug\app-debug.apk
```

If several devices are connected:

```cmd
%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe devices
%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe -s DEVICE_ID install -r android\app\build\outputs\apk\debug\app-debug.apk
```

## Build Play Store Bundle

```cmd
scripts\build_android_release.cmd
```

Output:

```text
android\app\build\outputs\bundle\release\app-release.aab
```

Publication details: `PLAY_STORE_PUBLISHING.md`
