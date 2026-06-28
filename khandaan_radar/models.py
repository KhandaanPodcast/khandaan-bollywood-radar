from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Story:
    title: str
    url: str
    platform: str
    summary: str = ""
    author: str = ""
    published_at: datetime | None = None
    score: float = 0.0
    comments: int = 0
    metadata: dict = field(default_factory=dict)
    priority_score: float = 0.0
    discussion_score: float = 0.0
    controversy_score: float = 0.0
    engagement_score: float = 0.0
    confidence_score: float = 0.0
    badges: list[str] = field(default_factory=list)
    output_recommendation: str = "Ignore"
    topic_category: str = "general Bollywood"
    best_use: str = "park for later"
    audience_temperature: str = "unclear"
    editorial_angle: str = ""
    suggested_hook: str = ""
    suggested_patron_poll: str = ""
    khandaan_take: str = ""
    image_url: str = ""
    trend_direction: str = "new"
    ranking_reasons: list[str] = field(default_factory=list)
    why_khandaan_should_care: str = ""
    discussion_questions: list[str] = field(default_factory=list)
    related_stories: list[dict[str, str]] = field(default_factory=list)
    lifecycle: str = "Developing"
    source_summary: dict[str, int] = field(default_factory=lambda: {
        "google_news": 0,
        "reddit": 0,
        "listener": 0,
    })
    confidence_explanation: str = ""

    @property
    def recency_hours(self) -> float:
        if not self.published_at:
            return 72.0
        published = self.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600)

    @property
    def age_label(self) -> str:
        if not self.published_at:
            return "age unknown"
        hours = self.recency_hours
        if hours < 1:
            return "under 1h old"
        if hours < 24:
            return f"{int(hours)}h old"
        days = max(1, int(hours / 24))
        return f"{days} day old" if days == 1 else f"{days} days old"


@dataclass
class Submission:
    story_link: str
    summary: str
    source_platform: str
    why_it_matters: str
    submitter_name: str
    credit_permission: bool
    patreon_member: bool
    duplicate_count: int = 1
    submitters: list[str] = field(default_factory=list)
    interest_score: float = 0.0
    recommendation: str = "podcast segment"
    priority_score: float = 0.0
    discussion_score: float = 0.0
    controversy_score: float = 0.0
    engagement_score: float = 0.0
    confidence_score: float = 0.0
    badges: list[str] = field(default_factory=list)
    output_recommendation: str = "Ignore"
    topic_category: str = "general Bollywood"
    best_use: str = "park for later"
    audience_temperature: str = "unclear"
    editorial_angle: str = ""
    suggested_hook: str = ""
    suggested_patron_poll: str = ""
    khandaan_take: str = ""
    image_url: str = ""
    trend_direction: str = "new"
    submitted_at: datetime | None = None

    @property
    def age_label(self) -> str:
        if not self.submitted_at:
            return "listener suggestion"
        submitted = self.submitted_at
        if submitted.tzinfo is None:
            submitted = submitted.replace(tzinfo=timezone.utc)
        hours = max(0.0, (datetime.now(timezone.utc) - submitted).total_seconds() / 3600)
        if hours < 1:
            return "submitted this hour"
        if hours < 24:
            return f"submitted {int(hours)}h ago"
        days = max(1, int(hours / 24))
        return f"submitted {days}d ago"
