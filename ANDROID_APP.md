# Cursor News Android

MVP natif Android pour lire Cursor News avec le texte au premier plan.

## Fonctionnalites v0.1

- Charge `manifest.json` et `news.json` depuis le bucket GCP public.
- Affiche les actualites texte avec recherche locale.
- Filtre par periode: 24 dernieres heures, aujourd'hui, 7 jours, tout.
- Masque les articles lus par defaut.
- Sauvegarde les articles lus dans les preferences Android.
- Mini-lecteur audio pour le flash en cours.
- Ouvre l'article source dans le navigateur du telephone.

## Build Windows

Android Studio et le SDK doivent etre installes. Le script force le JDK embarque d'Android Studio:

```cmd
scripts\build_android_debug.cmd
```

APK genere:

```text
android\app\build\outputs\apk\debug\app-debug.apk
```

## Installation sur telephone ou emulateur

```cmd
%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe install -r android\app\build\outputs\apk\debug\app-debug.apk
```

## Suite utile

- Ajouter une vraie navigation archive/detail.
- Ajouter un lecteur audio avec notification media.
- Ajouter des filtres region/source comme sur le site.
- Ajouter un mode hors-ligne avec cache local.
