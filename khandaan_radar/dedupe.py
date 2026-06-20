from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Story


TRACKING_PARAMS = {"fbclid", "gclid", "ref", "source"}


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS]
    host = parts.netloc.lower().removeprefix("www.")
    return urlunsplit((parts.scheme.lower() or "https", host, parts.path.rstrip("/"), urlencode(query), ""))


def normalized_title(title: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", title.lower()))


def deduplicate_stories(stories: list[Story], title_threshold: float = 0.88) -> list[Story]:
    unique: list[Story] = []
    seen_urls: set[str] = set()
    for story in sorted(stories, key=lambda item: item.score, reverse=True):
        url_key = canonical_url(story.url)
        title_key = normalized_title(story.title)
        duplicate = url_key in seen_urls if url_key else False
        if not duplicate and title_key:
            duplicate = any(
                SequenceMatcher(None, title_key, normalized_title(other.title)).ratio() >= title_threshold
                for other in unique
            )
        if duplicate:
            continue
        unique.append(story)
        if url_key:
            seen_urls.add(url_key)
    return unique

