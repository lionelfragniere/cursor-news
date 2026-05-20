# Cursor News

Prototype local et serveur de web-radio d'actualites automatisee. Cursor News collecte des flux RSS, stocke les articles dans SQLite, genere des bulletins thematiques avec un LLM local, produit de l'audio parle, puis publie l'interface web et les MP3 vers GCP.

## Demarrage rapide Windows

```cmd
scripts\setup_windows.cmd
scripts\run_server.cmd
```

Dans un deuxieme terminal :

```cmd
scripts\run_worker.cmd
```

Par defaut, l'interface ecoute sur `http://localhost:8000` et peut etre exposee sur le LAN via `0.0.0.0:8000`.

## Serveur Ubuntu autonome

Pour migrer sur le laptop serveur Ubuntu Desktop:

```cmd
scripts\prepare_ubuntu_usb_windows.cmd
```

Puis, sur Ubuntu dans le dossier du projet:

```bash
bash scripts/bootstrap_ubuntu.sh
bash scripts/run_tick_ubuntu.sh
bash scripts/install_systemd_ubuntu.sh
```

Le timer systemd lance un cycle complet chaque heure. La rotation de bulletins est thematique: Suisse romande, Valais, Suisse, International, ONU/Nations Unies, International English et Situation securitaire mondiale. Les MP3 sont encodes en mono 64 kbps et l'archive GCP ne garde que les bulletins recents. Le guide complet est dans `UBUNTU_SERVER_SETUP.md`.

## Commandes utiles

```cmd
uv run cursor-news init-db
uv run cursor-news ingest --once
uv run cursor-news generate --slot now
uv run cursor-news run
uv run cursor-news serve --host 0.0.0.0 --port 8000
uv run cursor-news upload --dry-run
uv run cursor-news stream --limit 5
uv run cursor-news export-autodj
uv run cursor-news publish-gcp --configure-cors
uv run cursor-news tick --publish-gcp
```

## Notes importantes

- Le profil cible est Windows CPU-only, avec Python 3.10.
- `ffmpeg` est installe localement par `scripts\setup_windows.cmd` dans `tools\ffmpeg\bin`.
- Coqui TTS CPU est installe par `scripts\setup_windows.cmd`.
- Le stream Infomaniak live utilise l'encodeur Icecast quand les variables `INFOMANIAK_STREAM_*` sont configurees.
- Pour eteindre le PC, utiliser `scripts\export_autodj.cmd`, importer le fichier `CursorNews_1h_loop.mp3` dans l'espace AOD Infomaniak, puis le faire boucler avec Auto DJ.
