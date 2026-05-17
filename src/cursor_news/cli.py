from __future__ import annotations

import argparse
import json
from datetime import datetime

import uvicorn

from .autodj import AutoDJExporter
from .gcp_publish import configure_gcp_bucket_cors, publish_to_gcp
from .pipeline import CursorNewsPipeline
from .settings import load_settings
from .site_export import export_site_news
from .streamer import InfomaniakIcecastStreamer
from .web import create_app
from .worker import run_worker


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cursor-news")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db")

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--once", action="store_true")

    generate = sub.add_parser("generate")
    generate.add_argument("--slot", default="buffer", choices=["now", "buffer"])

    serve = sub.add_parser("serve")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    sub.add_parser("run")

    upload = sub.add_parser("upload")
    upload.add_argument("--dry-run", action="store_true")

    metadata = sub.add_parser("metadata")
    metadata.add_argument("--dry-run", action="store_true")

    stream = sub.add_parser("stream")
    stream.add_argument("--once", action="store_true", help="Diffuse la playlist une seule fois au lieu de boucler.")
    stream.add_argument("--limit", type=int, default=12, help="Nombre de bulletins prets a mettre dans la playlist.")
    stream.add_argument("--duration-seconds", type=int, default=None, help="Limite de duree pour un test court.")
    stream.add_argument("--dry-run", action="store_true", help="Affiche la commande sans lancer ffmpeg.")

    autodj = sub.add_parser("export-autodj")
    autodj.add_argument("--output-dir", default=None)
    autodj.add_argument("--no-hour-loop", action="store_true")

    site = sub.add_parser("export-site-data")
    site.add_argument("--output", default="deploy/gcp-player/news.json")
    site.add_argument("--limit", type=int, default=400)
    site.add_argument("--include-sports", action="store_true")

    publish_gcp = sub.add_parser("publish-gcp")
    publish_gcp.add_argument("--news-limit", type=int, default=500)
    publish_gcp.add_argument("--configure-cors", action="store_true")

    tick = sub.add_parser("tick")
    tick.add_argument("--skip-ingest", action="store_true")
    tick.add_argument("--skip-generate", action="store_true")
    tick.add_argument("--publish-gcp", action="store_true")
    tick.add_argument("--news-limit", type=int, default=500)

    sub.add_parser("status")

    args = parser.parse_args(argv)
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)

    if args.command == "init-db":
        pipeline.init_db()
        print(f"Database ready: {settings.database_path}")
        return

    if args.command == "ingest":
        print(json.dumps(pipeline.ingest_once(), indent=2, ensure_ascii=False))
        return

    if args.command == "generate":
        if args.slot == "now":
            slot = pipeline.schedule.floor_slot(datetime.now())
            print(pipeline.generate_slot(slot))
        else:
            print(json.dumps(pipeline.generate_buffer(), indent=2, ensure_ascii=False))
        return

    if args.command == "serve":
        uvicorn.run(
            create_app(settings),
            host=args.host or settings.host,
            port=args.port or settings.port,
        )
        return

    if args.command == "run":
        run_worker()
        return

    if args.command == "upload":
        if not args.dry_run or not settings.infomaniak_dry_run:
            raise SystemExit("Only dry-run upload is implemented in v1.")
        print("\n".join(pipeline.upload_dry_run()))
        return

    if args.command == "metadata":
        print("\n".join(pipeline.publish_current_metadata(dry_run=args.dry_run or None)))
        return

    if args.command == "stream":
        streamer = InfomaniakIcecastStreamer(settings)
        plan = streamer.plan(
            limit=args.limit,
            loop=not args.once,
            duration_seconds=args.duration_seconds,
        )
        print(f"Playlist: {plan.playlist_path}")
        print(f"Bulletins: {len(plan.audio_paths)}")
        print("Commande: " + " ".join(plan.redacted_command))
        if args.dry_run:
            return
        raise SystemExit(streamer.run(limit=args.limit, loop=not args.once, duration_seconds=args.duration_seconds))

    if args.command == "export-autodj":
        export = AutoDJExporter(settings).export(
            output_dir=None if not args.output_dir else settings.home / args.output_dir,
            build_hour_loop=not args.no_hour_loop,
        )
        print(f"Export Auto DJ: {export.export_dir}")
        print(f"Fichiers creneaux: {len(export.slot_files)}")
        if export.loop_file:
            print(f"Boucle 1h: {export.loop_file}")
        print(f"Planning: {export.schedule_csv}")
        print(f"Instructions: {export.readme}")
        return

    if args.command == "export-site-data":
        output_path = settings.home / args.output
        payload = export_site_news(settings, output_path, limit=args.limit, include_sports=args.include_sports)
        print(f"Export site: {output_path}")
        print(f"Articles: {payload['count']}")
        return

    if args.command == "publish-gcp":
        if args.configure_cors:
            print("\n".join(configure_gcp_bucket_cors(settings)))
        print("\n".join(publish_to_gcp(settings, news_limit=args.news_limit)))
        return

    if args.command == "tick":
        result: dict[str, object] = {}
        if not args.skip_ingest:
            result["ingest"] = pipeline.ingest_once()
        if not args.skip_generate:
            result["generated"] = pipeline.generate_buffer()
        if args.publish_gcp:
            result["publish_gcp"] = publish_to_gcp(settings, news_limit=args.news_limit)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if args.command == "status":
        print(json.dumps(pipeline.db.status_snapshot(), indent=2, ensure_ascii=False))
        return
