from __future__ import annotations

from pathlib import Path

import yaml


DEFAULTS = {
    "google_news": {"enabled": True, "keywords": ["Bollywood"], "max_items_per_keyword": 10, "max_age_hours": 168},
    "reddit": {"enabled": False, "subreddits": [], "sort": "hot", "limit_per_subreddit": 15},
    "x_inputs": {"enabled": True, "file": "x_inputs.md"},
    "manual_watchlist": {"items": []},
    "watchlists": {
        "active_releases": [], "studios": [], "talent": [], "industry_themes": [],
        "ignore": [], "false_positive_exclusions": [],
    },
    "listener_submissions": {"source": "listener_submissions.csv"},
    "briefing": {"top_stories": 15, "max_per_google_keyword": 2, "max_per_subreddit": 3, "listener_items": 8},
}


def load_config(path: str | Path) -> tuple[dict, Path]:
    config_path = Path(path).expanduser().resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Source config not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config = {key: {**value, **(raw.get(key) or {})} for key, value in DEFAULTS.items()}
    return config, config_path.parent
