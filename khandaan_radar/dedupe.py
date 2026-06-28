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
        duplicate_of = next(
            (other for other in unique if url_key and canonical_url(other.url) == url_key),
            None,
        )
        if duplicate_of is None and title_key:
            duplicate_of = next(
                (
                    other for other in unique
                    if SequenceMatcher(None, title_key, normalized_title(other.title)).ratio() >= title_threshold
                ),
                None,
            )
        if duplicate_of is not None:
            duplicate_of.metadata["source_count"] = int(duplicate_of.metadata.get("source_count", 1)) + int(story.metadata.get("source_count", 1))
            continue
        story.metadata["source_count"] = max(1, int(story.metadata.get("source_count", 1)))
        unique.append(story)
        if url_key:
            seen_urls.add(url_key)
    return unique
