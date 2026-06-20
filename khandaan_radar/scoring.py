from __future__ import annotations

import math
import re

from .models import Story, Submission


POSITIVE = {"love", "loved", "hit", "praise", "excited", "success", "record", "winning", "best", "great", "strong"}
NEGATIVE = {"hate", "flop", "backlash", "controversy", "angry", "fail", "worst", "troll", "boycott", "disappoint", "slammed"}
SPECULATIVE = {"rumour", "rumor", "reportedly", "alleged", "possibly", "speculation", "buzz", "claims", "unconfirmed"}
CONFIRMED = {"official", "confirmed", "announced", "announces", "reporting", "statement", "released"}

CATEGORIES = (
    ("fan culture / controversy", {"fan war", "fandom", "stan", "troll", "boycott", "backlash", "controversy", "feud", "vs", "biggest star"}),
    ("industry / business", {"box office", "advance booking", "advance bookings", "budget", "studio", "producer", "distribution", "streaming", "ott", "deal", "industry", "business"}),
    ("trailer / music / craft", {"trailer", "teaser", "song", "music", "dance", "poster", "look", "visual", "vfx", "cinematography", "performance"}),
    ("casting / production", {"cast", "casting", "shoot", "director", "remake", "sequel", "project", "film announced", "signs"}),
    ("awards / festivals", {"award", "festival", "cannes", "oscar", "filmfare", "nomination", "jury"}),
    ("release / promotion", {"release", "premiere", "date", "promotion", "interview", "event"}),
)

BADGE_RULES = (
    ("Fan War", {"fan war", "fandom", "stan", "troll", "boycott", "feud", "biggest star"}),
    ("Industry Trend", {"industry", "studio", "strategy", "producer", "distribution", "budget", "cinema culture"}),
    ("Film Release", {"release", "premiere", "trailer", "teaser", "advance booking", "advance bookings"}),
    ("Streaming", {"streaming", "ott", "netflix", "prime video", "hotstar", "zee5"}),
    ("Casting", {"cast", "casting", "signs", "project", "next film", "next movie"}),
    ("Box Office", {"box office", "advance booking", "advance bookings", "collection", "collections", "opening weekend"}),
)


def _clamp(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 1)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _contains(text: str, terms: set[str]) -> bool:
    lowered = text.lower()
    words = _words(text)
    return any(term in lowered if " " in term else term in words for term in terms)


def classify_topic(text: str) -> str:
    for category, terms in CATEGORIES:
        if _contains(text, terms):
            return category
    return "general Bollywood"


def audience_temperature(text: str) -> str:
    positive = _contains(text, POSITIVE)
    negative = _contains(text, NEGATIVE)
    if positive and negative:
        return "mixed"
    if _contains(text, SPECULATIVE):
        return "speculative"
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "unclear"


def _badges(text: str, category: str, temperature: str) -> list[str]:
    badges = [label for label, terms in BADGE_RULES if _contains(text, terms)]
    if category == "fan culture / controversy" and "Fan War" not in badges:
        badges.append("Fan War")
    if category == "industry / business" and "Industry Trend" not in badges:
        badges.append("Industry Trend")
    if temperature == "speculative" or _contains(text, SPECULATIVE):
        badges.append("Rumour")
    return list(dict.fromkeys(badges))


def _controversy(text: str, category: str, temperature: str) -> float:
    value = 62.0 if category == "fan culture / controversy" else 18.0
    if temperature == "mixed":
        value += 24.0
    elif temperature == "negative":
        value += 18.0
    elif temperature == "speculative":
        value += 12.0
    if _contains(text, {"vs", "biggest", "nepotism", "boycott", "backlash", "feud"}):
        value += 16.0
    return _clamp(value)


def _confidence(text: str, platform: str, *, explanation_length: int = 0) -> float:
    lowered = platform.lower()
    if "google news" in lowered or lowered in {"news", "website"}:
        value = 76.0
    elif "youtube" in lowered or "instagram" in lowered:
        value = 62.0
    elif "reddit" in lowered:
        value = 48.0
    else:
        value = 54.0
    if _contains(text, CONFIRMED):
        value += 16.0
    if _contains(text, SPECULATIVE):
        value -= 28.0
    value += min(8.0, explanation_length / 40.0)
    return _clamp(value)


def _consequence(category: str, badges: list[str]) -> float:
    base = {
        "industry / business": 78.0,
        "fan culture / controversy": 70.0,
        "casting / production": 62.0,
        "trailer / music / craft": 58.0,
        "release / promotion": 55.0,
        "awards / festivals": 52.0,
    }.get(category, 46.0)
    if "Box Office" in badges:
        base += 8.0
    return _clamp(base)


def _recommend(category: str, badges: list[str], discussion: float, engagement: float, confidence: float, controversy: float, *, patreon: bool = False) -> str:
    if (confidence < 35 and discussion < 62) or discussion < 34:
        return "Ignore"
    if category == "trailer / music / craft":
        return "Reel" if engagement >= 45 or discussion >= 58 else "Shorts"
    if discussion >= 72 and confidence >= 45:
        return "Main Episode"
    if (patreon and discussion >= 50) or ("Industry Trend" in badges and discussion >= 57) or (controversy >= 72 and discussion >= 58):
        return "Patreon Discussion"
    if "Film Release" in badges and engagement >= 55:
        return "Shorts"
    if discussion >= 55:
        return "Main Episode"
    return "Newsletter"


def _legacy_best_use(recommendation: str) -> str:
    return {
        "Reel": "reel", "Shorts": "reel", "Main Episode": "podcast segment",
        "Patreon Discussion": "Patreon discussion", "Newsletter": "newsletter", "Ignore": "park for later",
    }[recommendation]


def _editorial_copy(title: str, category: str, temperature: str) -> tuple[str, str, str, str]:
    subject = " ".join(title.split()).strip().rstrip(".!?") or "This story"
    if category == "fan culture / controversy":
        angle = "Separate the actual story from the fandom fog, then ask who benefits from keeping the argument alive."
        hook = f"{subject}: real cultural flashpoint, or another exhausting shift at the fan-war factory?"
        poll = "Is this a meaningful debate, harmless fandom theatre, or a cue to log off?"
        if _contains(subject, {"biggest star", "biggest male star", "number one"}):
            take = "The 'biggest star' debate is Bollywood astrology: everyone has a chart, nobody agrees on the planets, and somehow the conclusion is always their favourite. What are we measuring?"
        elif _contains(subject, {"nepotism"}):
            take = "The nepotism conversation did not disappear; the audience just became more selective about when it matters. Apparently talent is still the most effective crisis-management strategy."
        else:
            take = "Look, the fandom has already arrived with charts, screenshots and a grievance. Before we declare a winner, can we establish what the argument is actually about?"
    elif category == "industry / business":
        angle = "Follow the money and incentives: what does this reveal about how Hindi cinema is being packaged, financed, or measured?"
        hook = f"The headline is {subject}, but the more interesting story may be the business decision underneath it."
        poll = "Will this industry move improve the films, improve the marketing, or merely improve the spreadsheet?"
        if _contains(subject, {"box office", "advance booking", "advance bookings", "collection", "collections"}):
            take = "The advance-booking screenshots are here, so apparently we are all trade analysts until Monday morning. The number is interesting; the panic or victory lap around it is usually more interesting."
        elif _contains(subject, {"streaming", "ott", "netflix", "prime video"}):
            take = "Every OTT debate becomes 'cinema is dying' within four replies. Maybe the better question is which films still make people leave the sofa, and why."
        elif _contains(subject, {"studio", "strategy", "reliable"}):
            take = "One hit and we immediately announce a new studio blueprint; one flop and we hold a funeral. Let us see whether there is a real strategy here or just hindsight with a PowerPoint."
        else:
            take = "This is where everybody says it is about cinema, right up until the spreadsheet enters the room. The numbers matter, but what story do they actually tell?"
    elif category == "trailer / music / craft":
        angle = "Move past instant hype and judge the craft: what is the material promising, and what might the campaign be carefully hiding?"
        hook = f"{subject}: genuine creative promise, clever trailer engineering, or both?"
        poll = "After this first look, are you seated, cautiously curious, or waiting for reviews?"
        take = "A trailer has two minutes to make us lose all critical judgment. Fine, job done. Now: does the film underneath it look any good?"
    elif category == "casting / production":
        angle = "Test the announcement against creative logic: does the talent fit the material, and is there enough confirmed fact to care yet?"
        hook = f"{subject}: inspired combination or a press release still searching for a movie?"
        poll = "Does this team-up excite you, worry you, or need more evidence?"
        take = "Bollywood can announce a cast years before it locates a script. I like the combination; I would also like one confirmed fact before planning the episode."
    elif category == "awards / festivals":
        angle = "Use the recognition to discuss taste, access, and the distance between industry prestige and audience memory."
        hook = f"{subject}: a meaningful win, an overdue correction, or awards-season positioning?"
        poll = "Does this recognition match your view: deserved, overdue, or baffling?"
        take = "Awards are subjective until our favourite wins, at which point they become a flawless instrument of justice. So, was this one actually deserved?"
    else:
        angle = "Identify what is confirmed, why audiences care now, and whether the story has enough consequence to survive the news cycle."
        hook = f"{subject}: the headline is loud, but is there a conversation underneath it?"
        poll = "Should Khandaan discuss this now, wait for more facts, or leave it alone?"
        take = "I can see why this is on the timeline. I am less convinced it can survive ten minutes of conversation without us asking, 'Yes, but what actually happened?'"
    if temperature == "speculative":
        angle += " Keep the rumour label firmly attached; enthusiasm is not verification."
        take += " Also, at the moment this is gossip wearing a blazer, so caveats please."
    return angle, hook, poll, take


def score_story(story: Story) -> Story:
    text = f"{story.title} {story.summary}"
    category = classify_topic(text)
    temperature = audience_temperature(text)
    badges = _badges(text, category, temperature)
    upvotes = max(0, int(story.metadata.get("upvotes", 0)))
    measured = math.log1p(upvotes) * 9.0 + math.log1p(max(0, story.comments)) * 12.0
    platform_floor = 48.0 if story.platform == "Reddit" else 42.0 if story.platform == "X (manual)" else 36.0
    engagement = _clamp(max(platform_floor, measured))
    confidence = _confidence(text, story.platform, explanation_length=len(story.summary))
    controversy = _controversy(text, category, temperature)
    consequence = _consequence(category, badges)
    recency = _clamp(100.0 - story.recency_hours * 2.2)
    priority = _clamp(recency * 0.28 + consequence * 0.32 + confidence * 0.24 + engagement * 0.16)
    discussion = _clamp(consequence * 0.30 + controversy * 0.25 + engagement * 0.22 + confidence * 0.13 + priority * 0.10)
    recommendation = _recommend(category, badges, discussion, engagement, confidence, controversy)

    story.priority_score = priority
    story.discussion_score = discussion
    story.controversy_score = controversy
    story.engagement_score = engagement
    story.confidence_score = confidence
    story.badges = badges
    story.output_recommendation = recommendation
    if story.recency_hours <= 12:
        story.trend_direction = "new"
    elif engagement >= 60 or discussion >= 60:
        story.trend_direction = "up"
    elif story.recency_hours >= 72 or recommendation == "Ignore":
        story.trend_direction = "down"
    else:
        story.trend_direction = "new"
    story.topic_category = category
    story.audience_temperature = temperature
    story.best_use = _legacy_best_use(recommendation)
    story.editorial_angle, story.suggested_hook, story.suggested_patron_poll, story.khandaan_take = _editorial_copy(story.title, category, temperature)
    story.score = discussion
    return story


def score_submission(item: Submission) -> Submission:
    text = f"{item.summary} {item.why_it_matters}"
    category = classify_topic(text)
    temperature = audience_temperature(text)
    badges = _badges(text, category, temperature)
    engagement = _clamp(24.0 + item.duplicate_count * 18.0 + (10.0 if item.patreon_member else 0.0) + min(18.0, len(item.why_it_matters) / 8.0))
    confidence = _confidence(text, item.source_platform, explanation_length=len(item.why_it_matters))
    controversy = _controversy(text, category, temperature)
    consequence = _consequence(category, badges)
    priority = _clamp(consequence * 0.34 + confidence * 0.28 + engagement * 0.26 + (12.0 if item.patreon_member else 4.0))
    discussion = _clamp(consequence * 0.29 + controversy * 0.27 + engagement * 0.25 + confidence * 0.12 + priority * 0.07)
    recommendation = _recommend(category, badges, discussion, engagement, confidence, controversy, patreon=item.patreon_member)

    item.priority_score = priority
    item.discussion_score = discussion
    item.controversy_score = controversy
    item.engagement_score = engagement
    item.confidence_score = confidence
    item.badges = badges
    item.output_recommendation = recommendation
    if item.duplicate_count > 1 or engagement >= 60 or discussion >= 60:
        item.trend_direction = "up"
    elif recommendation == "Ignore":
        item.trend_direction = "down"
    else:
        item.trend_direction = "new"
    item.interest_score = discussion
    item.topic_category = category
    item.audience_temperature = temperature
    item.best_use = _legacy_best_use(recommendation)
    item.recommendation = item.best_use
    item.editorial_angle, item.suggested_hook, item.suggested_patron_poll, item.khandaan_take = _editorial_copy(item.summary, category, temperature)
    return item


def rank_stories(items: list[Story]) -> list[Story]:
    return sorted((score_story(item) for item in items), key=lambda item: (item.discussion_score, item.priority_score), reverse=True)


def rank_submissions(items: list[Submission]) -> list[Submission]:
    return sorted((score_submission(item) for item in items), key=lambda item: (item.discussion_score, item.priority_score), reverse=True)


def apply_ai_enrichment(items: list[Story], submissions: list[Submission], editorial: dict) -> None:
    story_edits = editorial.get("story_enrichments", {})
    submission_edits = editorial.get("submission_enrichments", {})
    for item in items:
        edit = story_edits.get(item.title, {})
        item.editorial_angle = edit.get("editorial_angle") or item.editorial_angle
        item.suggested_hook = edit.get("suggested_hook") or item.suggested_hook
        item.suggested_patron_poll = edit.get("suggested_patron_poll") or item.suggested_patron_poll
        item.khandaan_take = edit.get("khandaan_take") or item.khandaan_take
    for item in submissions:
        edit = submission_edits.get(item.summary, {})
        item.editorial_angle = edit.get("editorial_angle") or item.editorial_angle
        item.suggested_hook = edit.get("suggested_hook") or item.suggested_hook
        item.suggested_patron_poll = edit.get("suggested_patron_poll") or item.suggested_patron_poll
        item.khandaan_take = edit.get("khandaan_take") or item.khandaan_take
