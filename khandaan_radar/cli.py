from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

from .briefing import render_briefing
from .config import load_config
from .dashboard import render_dashboard
from .dedupe import deduplicate_stories
from .fetchers import fetch_google_news, fetch_reddit, read_x_inputs
from .intelligence import enrich_story_intelligence
from .scoring import rank_stories, rank_submissions, select_diverse_stories
from .submissions import group_submissions, load_submissions, resolve_submission_source
from .summarizer import fallback_editorial


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a local Bollywood editorial briefing.")
    parser.add_argument("--sources", default="sources.yaml", help="Path to sources YAML")
    parser.add_argument("--output", default="briefing.md", help="Markdown export path")
    parser.add_argument("--dashboard", default="dashboard.html", help="Primary HTML dashboard path")
    parser.add_argument("--share-output", default="share_dashboard.html", help="Single-file static share export")
    parser.add_argument("--public-output", default="public/index.html", help="Public-hosting-ready page")
    parser.add_argument("--root-output", default="index.html", help="GitHub Pages homepage at the repository root")
    parser.add_argument("--public-url", default="", help="Hosted dashboard URL used by the Share button")
    parser.add_argument("--no-ai", action="store_true", help="Deprecated compatibility flag; editorial intelligence is always metadata-based")
    parser.add_argument("--offline", action="store_true", help="Skip Google News and Reddit network calls")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    load_dotenv()
    try:
        config, base_dir = load_config(args.sources)
        warnings: list[str] = []
        news = []
        reddit = []
        if not args.offline:
            try:
                news = fetch_google_news(config["google_news"])
            except Exception as exc:
                warnings.append(f"Google News skipped: {exc}")
            try:
                reddit = fetch_reddit(config["reddit"])
            except Exception as exc:
                warnings.append(f"Reddit skipped: {exc}")
        x_items = []
        if config["x_inputs"].get("enabled", True):
            x_path = _resolve(base_dir, config["x_inputs"]["file"])
            x_items = read_x_inputs(x_path)
        submission_source = resolve_submission_source(config["listener_submissions"].get("source", ""))
        submissions = group_submissions(load_submissions(submission_source, base_dir, warnings=warnings)) if submission_source else []

        watchlists = config.get("watchlists") or config["manual_watchlist"].get("items", [])
        ranked_stories = select_diverse_stories(
            rank_stories([*deduplicate_stories(news), *deduplicate_stories(reddit)], watchlists),
            int(config["briefing"]["top_stories"]),
            max_per_google_keyword=int(config["briefing"].get("max_per_google_keyword", 2)),
            max_per_subreddit=int(config["briefing"].get("max_per_subreddit", 3)),
        )
        news = [story for story in ranked_stories if story.platform == "Google News"]
        reddit = [story for story in ranked_stories if story.platform == "Reddit"]
        x_items = rank_stories(deduplicate_stories(x_items), watchlists)
        submissions = rank_submissions(submissions)[: int(config["briefing"]["listener_items"])]
        enrich_story_intelligence([*news, *reddit, *x_items], submissions)
        editorial = fallback_editorial()
        output = _resolve(Path.cwd(), args.output)
        dashboard = _resolve(Path.cwd(), args.dashboard)
        share_output = _resolve(Path.cwd(), args.share_output)
        public_output = _resolve(Path.cwd(), args.public_output)
        root_output = _resolve(Path.cwd(), args.root_output)
        public_url = args.public_url or os.getenv("DASHBOARD_PUBLIC_URL", "")
        output.parent.mkdir(parents=True, exist_ok=True)
        dashboard.parent.mkdir(parents=True, exist_ok=True)
        share_output.parent.mkdir(parents=True, exist_ok=True)
        public_output.parent.mkdir(parents=True, exist_ok=True)
        root_output.parent.mkdir(parents=True, exist_ok=True)
        render_briefing(output, news, reddit, x_items, submissions, editorial)
        render_dashboard(
            dashboard, news, reddit, x_items, submissions, markdown_path=output,
            self_contained=True, fetch_images=not args.offline, public_url=public_url,
        )
        render_dashboard(
            share_output, news, reddit, x_items, submissions,
            self_contained=True, fetch_images=not args.offline, public_url=public_url,
        )
        render_dashboard(
            public_output, news, reddit, x_items, submissions,
            self_contained=True, fetch_images=not args.offline, public_url=public_url,
        )
        publish_root_homepage(public_output, root_output)
        print(f"Dashboard: {dashboard}")
        print(f"Share file: {share_output}")
        print(f"Public-ready page: {public_output}")
        print(f"Site root page: {root_output}")
        print(f"Public URL: {public_url or 'set DASHBOARD_PUBLIC_URL after uploading'}")
        print(f"Markdown export: {output}")
        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def publish_root_homepage(public_output: Path, root_output: Path) -> None:
    shutil.copyfile(public_output, root_output)
