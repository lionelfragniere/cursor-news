# Cursor News sur laptop Ubuntu

Ce guide prépare un laptop Ubuntu Desktop pour faire tourner Cursor News en autonomie:

- scrape RSS régulier;
- génération de bulletins toutes les 10 minutes;
- voix féminine française via Edge TTS;
- publication GCP de `current/live.mp3`, du transcript et des news scrappées;
- site Cloud Run toujours alimenté par les fichiers publics du bucket GCS.

## OS recommandé

Installe Ubuntu Desktop 26.04 LTS sur le laptop serveur. C'est la dernière LTS Desktop disponible, avec cinq ans de mises à jour de sécurité et maintenance gratuites. Ubuntu recommande au minimum un processeur double coeur 2 GHz, 6 Go de RAM, 25 Go de disque, un port USB et une connexion Internet.

Sources:

- https://ubuntu.com/download/desktop
- https://docs.cloud.google.com/sdk/docs/install-sdk

## 1. Préparer la clé USB depuis ce PC Windows

Depuis `D:\Cursor News`:

```cmd
scripts\prepare_ubuntu_usb_windows.cmd
```

Le script télécharge l'ISO officielle Ubuntu Desktop 26.04 LTS et affiche le hash SHA256 local ainsi que le hash officiel attendu. Il n'écrit pas sur la clé USB.

Ensuite:

1. Ouvre Rufus ou BalenaEtcher.
2. Sélectionne `ubuntu-26.04-desktop-amd64.iso`.
3. Choisis la clé USB cible.
4. Démarre le laptop sur la clé USB.
5. Installe Ubuntu Desktop.

## 2. Réglages Ubuntu après installation

Garde le laptop branché au secteur. Dans les réglages Ubuntu, désactive la mise en veille automatique et vérifie que la connexion réseau revient bien après redémarrage.

Option serveur dédié, si le laptop doit rester allumé même écran fermé:

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

## 3. Copier le projet

Copie ce dossier sur le laptop, par exemple dans:

```text
~/Cursor News
```

Les dossiers et fichiers importants à migrer sont:

- `.env`
- `config/`
- `data/` si tu veux garder l'historique existant

Sur Ubuntu, vérifie surtout ces valeurs dans `.env`:

```env
CURSOR_NEWS_HOME=.
FFMPEG_PATH=
GCLOUD_PATH=gcloud
GCP_PROJECT_ID=cursor-news-radio-20260517
GCP_BUCKET=gs://cursor-news-radio-20260517-audio
GCP_PUBLIC_BASE_URL=https://storage.googleapis.com/cursor-news-radio-20260517-audio
TTS_ENGINE=edge
EDGE_TTS_VOICE=fr-CH-ArianeNeural
OLLAMA_MODEL=qwen3:14b
```

## 4. Installer les dépendances

Depuis le dossier du projet:

```bash
bash scripts/bootstrap_ubuntu.sh
```

Le script installe:

- `ffmpeg`;
- `uv`;
- Google Cloud CLI;
- Ollama;
- Python 3.10 via `uv`;
- les dépendances Python du projet.

Puis configure GCP et le modèle local:

```bash
gcloud auth login
gcloud config set project cursor-news-radio-20260517
ollama pull qwen3:14b
```

## 5. Test manuel complet

Lance un cycle complet:

```bash
bash scripts/run_tick_ubuntu.sh
```

Ce cycle fait:

1. ingestion RSS;
2. génération du tampon de bulletins;
3. création audio MP3;
4. publication GCP de l'audio courant, du manifest et des news.

Vérifie ensuite:

```bash
bash scripts/check_ubuntu_server.sh
```

## 6. Automatisation 6 fois par heure

Installe le timer systemd utilisateur:

```bash
bash scripts/install_systemd_ubuntu.sh
```

Le timer lance `cursor-news tick --publish-gcp` à `00, 10, 20, 30, 40, 50` de chaque heure. Il utilise `Persistent=true`, donc un tick manqué est rattrapé après redémarrage.

Commandes utiles:

```bash
systemctl --user status cursor-news-tick.timer
systemctl --user list-timers cursor-news-tick.timer
journalctl --user -u cursor-news-tick.service -n 120 --no-pager
```

## 7. Site public

Le site Cloud Run sert l'interface. Les données dynamiques viennent du bucket:

- `current/news.json`
- `current/manifest.json`
- `current/live.mp3`
- `bulletins/{id}.mp3`

La page publique actuelle est:

```text
https://cursor-news-player-801987419922.europe-west6.run.app
```

## 8. Inclusivité

Le site expose déjà:

- lecteur audio;
- transcript du bulletin courant;
- historique d'articles filtrable;
- filtre enfant;
- filtre tension;
- masquage des articles lus.

Les prochaines améliorations utiles:

- mode texte agrandi;
- contraste renforcé;
- résumé très simple pour chaque article;
- filtre "bonnes nouvelles / solutions";
- version audio courte de chaque article;
- clavier uniquement, avec focus visible partout.

