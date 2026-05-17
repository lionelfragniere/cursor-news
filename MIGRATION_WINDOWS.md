# Migration Windows CPU-only

Cette app est developpee sur ce PC, puis migrable vers un laptop Windows Intel Core i7 sans GPU.

## 1. Preparer le laptop

Installer :

- Python 3.10
- uv
- Ollama

`ffmpeg` sera installe localement par le script de setup.

Verifier :

```cmd
py -0p
uv --version
ollama list
tools\ffmpeg\bin\ffmpeg.exe -version
```

Le modele LLM attendu par defaut est `qwen3:14b`. Si absent :

```cmd
ollama pull qwen3:14b
```

## 2. Copier le projet

Copier tout le dossier Cursor News vers le laptop. Les donnees migrables sont :

- `.env`
- `config\`
- `data\`

Les chemins doivent rester relatifs quand c'est possible. Si `ffmpeg` n'est pas dans le PATH, definir `FFMPEG_PATH` dans `.env`.

## 3. Installer

```cmd
scripts\setup_windows.cmd
```

## 4. Lancer en LAN

Terminal serveur :

```cmd
scripts\run_server.cmd
```

Terminal worker :

```cmd
scripts\run_worker.cmd
```

Depuis une autre machine du LAN, ouvrir :

```text
http://IP_DU_LAPTOP:8000
```

## 5. Demarrage automatique via Task Scheduler

Creer deux taches au demarrage ou a l'ouverture de session :

- `Cursor News Server` : `scripts\run_server.cmd`
- `Cursor News Worker` : `scripts\run_worker.cmd`

Configurer le dossier de demarrage sur la racine du projet. Activer le redemarrage automatique en cas d'echec.

## 6. Infomaniak

Le mode live envoie l'audio depuis le PC vers Infomaniak. Le PC doit rester allume :

```cmd
scripts\run_stream.cmd
```

Le mode Auto DJ permet d'eteindre le PC apres upload :

```cmd
scripts\export_autodj.cmd
```

Importer ensuite le fichier `CursorNews_1h_loop.mp3` genere dans `data\autodj\...\` vers l'espace AOD Infomaniak, puis creer une playlist Auto DJ qui boucle ce fichier. Pour conserver l'alignement 00/10/20/30/40/50, programmer le demarrage au debut d'une heure.
