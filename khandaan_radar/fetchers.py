from __future__ import annotations

import os
import re
from html import unescape
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

from .models import Story


def _feed_image(entry: dict) -> str:
    for key in ("media_content", "media_thumbnail"):
        values = entry.get(key) or []
        if values and isinstance(values[0], dict) and values[0].get("url"):
            return unescape(values[0]["url"])
    match = re.search(r'<img[^>]+src=["\']([^"\']+)', entry.get("summary", ""), flags=re.IGNORECASE)
    return unescape(match.group(1)) if match else ""


def _reddit_image(post: dict) -> str:
    previews = post.get("preview", {}).get("images", [])
    if previews:
        source = previews[0].get("source", {}).get("url", "")
        if source:
            return unescape(source)
    thumbnail = post.get("thumbnail", "")
    if thumbnail.startswith(("http://", "https://")):
        return unescape(thumbnail)
    external = post.get("url_overridden_by_dest", "")
    if re.search(r"\.(?:jpe?g|png|webp)(?:\?|$)", external, flags=re.IGNORECASE):
        return external
    return ""


def _rank_story(story: Story) -> float:
    recency = max(0.0, 72.0 - story.recency_hours) / 12.0
    engagement = min(12.0, story.score / 1000.0) + min(8.0, story.comments / 100.0)
    return round(recency + engagement + (1.0 if story.summary else 0.0), 2)


def fetch_google_news(config: dict, timeout: int = 15) -> list[Story]:
    import feedparser
    import requests

    if not config.get("enabled", True):
        return []
    language = config.get("language", "en-IN")
    country = config.get("country", "IN")
    limit = int(config.get("max_items_per_keyword", 10))
    stories: list[Story] = []
    for keyword in config.get("keywords", ["Bollywood"]):
        url = f"https://news.google.com/rss/search?q={quote_plus(keyword)}&hl={language}&gl={country}&ceid={country}:en"
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "KhandaanBollywoodRadar/0.1"})
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        for entry in feed.entries[:limit]:
            published = None
            if entry.get("published"):
                try:
                    published = parsedate_to_datetime(entry.published)
                except (TypeError, ValueError):
                    pass
            story = Story(
                title=entry.get("title", "Untitled"),
                url=entry.get("link", ""),
                platform="Google News",
                summary=re.sub(r"<[^>]+>", "", entry.get("summary", "")),
                published_at=published,
                metadata={"keyword": keyword},
                image_url=_feed_image(entry),
            )
            story.score = _rank_story(story)
            stories.append(story)
    return stories


def fetch_reddit(config: dict, timeout: int = 15) -> list[Story]:
    import requests

    if not config.get("enabled", False):
        return []
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "khandaan-bollywood-radar/0.1")
    if not client_id or not client_secret:
        raise RuntimeError("Reddit is enabled but REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are not set")
    token_response = requests.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )
    token_response.raise_for_status()
    token = token_response.json()["access_token"]
    headers = {"Authorization": f"bearer {token}", "User-Agent": user_agent}
    sort = config.get("sort", "hot")
    limit = int(config.get("limit_per_subreddit", 15))
    stories: list[Story] = []
    for subreddit in config.get("subreddits", []):
        response = requests.get(
            f"https://oauth.reddit.com/r/{subreddit}/{sort}",
            params={"limit": limit, "raw_json": 1},
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        for child in response.json().get("data", {}).get("children", []):
            post = child.get("data", {})
            created = datetime.fromtimestamp(post.get("created_utc", 0), tz=timezone.utc)
            story = Story(
                title=post.get("title", "Untitled"),
                url=f"https://www.reddit.com{post.get('permalink', '')}",
                platform="Reddit",
                summary=post.get("selftext", "")[:1000],
                author=post.get("author", ""),
                published_at=created,
                score=float(post.get("score", 0)),
                comments=int(post.get("num_comments", 0)),
                metadata={
                    "subreddit": subreddit,
                    "external_url": post.get("url_overridden_by_dest", ""),
                    "upvotes": int(post.get("score", 0)),
                },
                image_url=_reddit_image(post),
            )
            story.score = _rank_story(story)
            stories.append(story)
    return stories


def read_x_inputs(path: str | Path) -> list[Story]:
    input_path = Path(path)
    if not input_path.exists():
        return []
    stories: list[Story] = []
    for raw_line in input_path.read_text(encoding="utf-8").splitlines():
        line = re.sub(r"^\s*[-*+]\s*", "", raw_line).strip()
        if not line or line.startswith("#") or line.lower().startswith("paste one"):
            continue
        match = re.search(r"https?://(?:www\.)?(?:x\.com|twitter\.com)/\S+", line)
        url = match.group(0).rstrip(".,)") if match else ""
        title = line if len(line) <= 180 else line[:177] + "..."
        stories.append(
            Story(
                title=title,
                url=url,
                platform="X (manual)",
                summary=line,
                published_at=datetime.now(timezone.utc),
                score=1.0,
            )
        )
    return stories
