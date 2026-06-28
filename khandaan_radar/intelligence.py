from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Story, Submission


RELATION_STOPWORDS = {
    "a", "about", "after", "an", "and", "as", "at", "bollywood", "by", "day",
    "film", "for", "from", "has", "hindi", "in", "india", "indian", "is", "its",
    "movie", "new", "of", "on", "says", "story", "the", "to", "update", "with",
}


def _canonical_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid", "ref", "source"}
    ]
    return urlunsplit((parts.scheme.lower() or "https", parts.netloc.lower().removeprefix("www."), parts.path.rstrip("/"), urlencode(query), ""))


def _tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in RELATION_STOPWORDS
    }


def _watchlist_keys(story: Story) -> set[str]:
    keys = set()
    for match in story.metadata.get("watchlist_matches", []):
        cleaned = re.sub(r"\s*\(P[123]\)\s*$", "", str(match), flags=re.IGNORECASE)
        keys.add(cleaned.split(":", 1)[-1].strip().lower())
    return keys


def _relationship(left: Story, right: Story) -> tuple[float, str] | None:
    left_url = _canonical_url(left.url)
    right_url = _canonical_url(right.url)
    if left_url and left_url == right_url:
        return 1.0, "Same source URL"

    shared_watchlist = _watchlist_keys(left) & _watchlist_keys(right)
    if shared_watchlist:
        label = sorted(shared_watchlist)[0]
        return 0.95, f"Shared watchlist signal: {label}"

    left_tokens = _tokens(f"{left.title} {left.summary}")
    right_tokens = _tokens(f"{right.title} {right.summary}")
    shared = left_tokens & right_tokens
    if len(shared) < 2:
        return None
    overlap = len(shared) / max(1, min(len(left_tokens), len(right_tokens)))
    if overlap < 0.28 and len(shared) < 3:
        return None
    terms = ", ".join(sorted(shared)[:3])
    topic_bonus = 0.1 if left.topic_category == right.topic_category else 0.0
    return min(0.9, overlap + topic_bonus), f"Shared story terms: {terms}"


def _listener_matches(story: Story, submission: Submission) -> bool:
    story_url = _canonical_url(story.url)
    submission_url = _canonical_url(submission.story_link)
    if story_url and story_url == submission_url:
        return True
    story_tokens = _tokens(f"{story.title} {story.summary}")
    listener_tokens = _tokens(f"{submission.summary} {submission.why_it_matters}")
    shared = story_tokens & listener_tokens
    return len(shared) >= 2 and len(shared) / max(1, min(len(story_tokens), len(listener_tokens))) >= 0.3


def _lifecycle(story: Story) -> str:
    sources = story.source_summary
    channels = sum(count > 0 for count in sources.values())
    total = sum(sources.values())
    if story.output_recommendation == "Ignore" or (story.published_at is not None and story.recency_hours >= 72):
        return "Fading"
    if channels >= 2 and total >= 2 and (story.discussion_score >= 60 or story.engagement_score >= 60):
        return "Peaking"
    if story.published_at is not None and story.recency_hours <= 12:
        return "Breaking"
    return "Developing"


def confidence_explanation(story: Story) -> str:
    text = f"{story.title} {story.summary}".lower()
    platform = story.platform.lower()
    if "google news" in platform or platform in {"news", "website"}:
        basis = "Google News source baseline"
    elif "reddit" in platform:
        basis = "Reddit audience-post baseline"
    elif "youtube" in platform or "instagram" in platform:
        basis = "first-party social/video baseline"
    else:
        basis = f"{story.platform or 'manual source'} baseline"

    factors = [basis]
    if any(term in text for term in ("official", "confirmed", "announced", "announces", "statement", "released")):
        factors.append("confirmed-language present")
    if any(term in text for term in ("rumour", "rumor", "reportedly", "alleged", "possibly", "speculation", "unconfirmed")):
        factors.append("speculative-language penalty")
    factors.append("summary detail included" if story.summary else "no summary detail")

    sources = story.source_summary
    source_line = (
        f"Dashboard corroboration: {sources['google_news']} Google News, "
        f"{sources['reddit']} Reddit, {sources['listener']} listener."
    )
    return f"{story.confidence_score:.0f}/100 from {', '.join(factors)}. {source_line}"


def enrich_story_intelligence(stories: list[Story], submissions: list[Submission]) -> None:
    """Add relationships and lifecycle signals using only items already on the dashboard."""
    for story in stories:
        relationships: list[tuple[float, Story, str]] = []
        related_cluster = [story]
        for candidate in stories:
            if candidate is story:
                continue
            relation = _relationship(story, candidate)
            if relation is None:
                continue
            score, reason = relation
            relationships.append((score, candidate, reason))
            related_cluster.append(candidate)

        relationships.sort(key=lambda item: (item[0], item[1].discussion_score), reverse=True)
        story.related_stories = [
            {
                "title": candidate.title,
                "url": candidate.url,
                "platform": candidate.platform,
                "relationship": reason,
            }
            for _, candidate, reason in relationships[:3]
        ]
        story.source_summary = {
            "google_news": sum(
                int(item.metadata.get("source_count", 1)) for item in related_cluster if item.platform == "Google News"
            ),
            "reddit": sum(
                int(item.metadata.get("source_count", 1)) for item in related_cluster if item.platform == "Reddit"
            ),
            "listener": sum(
                submission.duplicate_count for submission in submissions if _listener_matches(story, submission)
            ),
        }
        story.lifecycle = _lifecycle(story)
        story.confidence_explanation = confidence_explanation(story)
