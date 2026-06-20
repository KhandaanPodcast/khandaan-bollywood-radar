from __future__ import annotations

from pathlib import Path

import yaml


DEFAULTS = {
    "google_news": {"enabled": True, "keywords": ["Bollywood"], "max_items_per_keyword": 10},
    "reddit": {"enabled": False, "subreddits": [], "sort": "hot", "limit_per_subreddit": 15},
    "x_inputs": {"file": "x_inputs.md"},
    "listener_submissions": {"source": "listener_submissions.csv"},
    "briefing": {"top_stories": 8, "reddit_items": 6, "listener_items": 8},
}


def load_config(path: str | Path) -> tuple[dict, Path]:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Source config not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config = {key: {**value, **(raw.get(key) or {})} for key, value in DEFAULTS.items()}
    return config, config_path.parent

