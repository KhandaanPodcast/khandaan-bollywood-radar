from __future__ import annotations

import math
import re
from datetime import date

from .intelligence import confidence_explanation
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


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _entry_name(entry: str | dict) -> str:
    if isinstance(entry, dict):
        return str(entry.get("title") or entry.get("name") or entry.get("term") or "")
    return str(entry)


def _entry_terms(entry: str | dict) -> list[str]:
    name = _entry_name(entry)
    aliases = entry.get("aliases", []) if isinstance(entry, dict) else []
    terms = entry.get("terms", []) if isinstance(entry, dict) else []
    return [term for term in [name, *aliases, *terms] if str(term).strip()]


def _text_matches(text: str, terms: list[str], exclusions: list[str] | None = None) -> bool:
    padded = f" {_normalized(text)} "
    if any(_normalized(term) == "war 2" for term in terms):
        exclusions = [*(exclusions or []), "World War 2", "World War II", "WW2", "WWII", "Second World War"]
    if any(f" {_normalized(term)} " in padded for term in (exclusions or []) if _normalized(term)):
        return False
    return any(f" {_normalized(term)} " in padded for term in terms if _normalized(term))


def _major_new_story(text: str) -> bool:
    return _contains(text, {
        "official", "confirmed", "announced", "trailer", "teaser", "release date", "casting",
        "box office", "collection", "record", "controversy", "backlash", "censor", "banned",
        "lawsuit", "flop", "hit", "reshoot", "delayed", "postponed",
    })


def _structured_watchlist_signals(text: str, watchlists: dict | list[str] | None) -> tuple[list[str], float, float]:
    if not watchlists:
        return [], 0.0, 0.0
    if isinstance(watchlists, list):
        matches = [_entry_name(item) for item in watchlists if _text_matches(text, _entry_terms(item))]
        return matches, min(12.0, len(matches) * 6.0), 0.0

    exclusion_map = {
        _normalized(_entry_name(entry)): entry.get("patterns", [])
        for entry in watchlists.get("false_positive_exclusions", [])
        if isinstance(entry, dict)
    }
    matches = []
    boost = 0.0
    today = date.today()

    for entry in watchlists.get("active_releases", []):
        name = _entry_name(entry)
        if not _text_matches(text, _entry_terms(entry), exclusion_map.get(_normalized(name), [])):
            continue
        release_date = entry.get("release_date") if isinstance(entry, dict) else None
        if release_date:
            try:
                days_until = (date.fromisoformat(str(release_date)) - today).days
            except ValueError:
                days_until = None
            if days_until is not None and days_until < 0:
                continue
        else:
            days_until = None
        priority = str(entry.get("priority", "P3")).upper() if isinstance(entry, dict) else "P3"
        value = {"P1": 10.0, "P2": 6.0, "P3": 2.0}.get(priority, 2.0)
        if days_until is not None:
            value += 3.0 if days_until <= 30 else 2.0 if days_until <= 90 else 1.0 if days_until <= 180 else 0.0
        matches.append(f"release: {name} ({priority})")
        boost += value

    for key, value in (("studios", 3.0), ("talent", 2.0), ("industry_themes", 3.0)):
        for entry in watchlists.get(key, []):
            name = _entry_name(entry)
            if _text_matches(text, _entry_terms(entry), exclusion_map.get(_normalized(name), [])):
                matches.append(f"{key.rstrip('s')}: {name}")
                boost += value

    penalty = 0.0
    for entry in watchlists.get("ignore", []):
        name = _entry_name(entry)
        if not _text_matches(text, _entry_terms(entry), exclusion_map.get(_normalized(name), [])):
            continue
        if isinstance(entry, dict) and entry.get("allow_major_new_story", False) and _major_new_story(text):
            matches.append(f"stale title with major new story: {name}")
        else:
            penalty += float(entry.get("penalty", 12.0)) if isinstance(entry, dict) else 12.0
            matches.append(f"de-prioritised: {name}")
    return list(dict.fromkeys(matches)), min(16.0, boost), min(24.0, penalty)


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


def _editorial_signal_adjustment(text: str) -> tuple[float, float, list[str]]:
    boost = 0.0
    penalty = 0.0
    reasons = []
    positive_signals = (
        ("controversy/backlash", {"controversy", "backlash", "boycott", "feud", "fan war"}, 6.0),
        ("box-office consequence", {"box office", "advance booking", "collection", "opening day", "record"}, 6.0),
        ("studio strategy", {"studio strategy", "distribution", "merger", "acquisition", "slate"}, 4.0),
        ("franchise discussion", {"franchise", "sequel", "part 2", "part 3", "part 4", "reboot"}, 4.0),
        ("star-power debate", {"star power", "stardom", "superstar", "biggest star"}, 4.0),
    )
    routine_signals = (
        ("poster/photo release", {"poster", "photos", "wallpapers", "images", "first look photos"}, 10.0),
        ("song release", {"song", "song released", "song out", "song from", "music video", "audio launch"}, 8.0),
        ("BTS material", {"bts", "behind the scenes", "set photos"}, 7.0),
        ("routine production update", {"additional shoot", "shoot begins", "shoot starts", "filming begins", "schedule update", "wraps shoot"}, 7.0),
    )
    for label, terms, value in positive_signals:
        if _contains(text, terms):
            boost += value
            reasons.append(label)
    for label, terms, value in routine_signals:
        if _contains(text, terms):
            penalty += value
            reasons.append(f"lower value: {label}")
    return min(14.0, boost), min(16.0, penalty), reasons


def _why_khandaan_should_care(
    text: str,
    category: str,
    controversy: float,
    matches: list[str],
) -> str:
    lowered_matches = " ".join(matches).lower()
    sentences = []
    if controversy >= 70 or _contains(text, {"backlash", "controversy", "fan war", "boycott", "feud", "vs"}):
        sentences.append("The story supports a clear debate about audience reaction and has measurable fan-war potential.")
    if _contains(text, {"box office", "advance booking", "collection", "opening day", "record"}) or "box office narratives" in lowered_matches:
        sentences.append("Its performance claims connect box-office narratives to expectations around stars, genres, or franchises.")
    if _contains(text, {"studio", "strategy", "distribution", "merger", "acquisition"}) or "studio:" in lowered_matches:
        sentences.append("The underlying decisions provide evidence for a discussion about studio strategy and control of Hindi-film production or distribution.")
    if _contains(text, {"franchise", "sequel", "part 2", "part 3", "part 4", "reboot"}) or any(term in lowered_matches for term in ("franchise fatigue", "sequel culture")):
        sentences.append("The title creates a concrete route into franchise fatigue, sequel culture, and the value of familiar intellectual property.")
    if _contains(text, {"representation", "female-led", "women-led", "woman-led"}) or "female-led action films" in lowered_matches:
        sentences.append("The casting or positioning supplies a specific representation question rather than a general promotional claim.")
    if _contains(text, {"nostalgia", "comeback", "reunion", "legacy"}) or "bollywood nostalgia" in lowered_matches:
        sentences.append("The story links Bollywood nostalgia to current audience demand and the commercial use of legacy talent or titles.")
    if _contains(text, {"star power", "stardom", "superstar", "biggest star"}) or "talent:" in lowered_matches:
        sentences.append("The named talent makes this useful for testing how star power shapes attention, marketing, and audience expectations.")
    if not sentences:
        fallback = {
            "industry / business": "The metadata points to an industry implication involving financing, distribution, streaming, or theatrical performance.",
            "casting / production": "The confirmed production details create a debate about casting logic and the project’s commercial positioning.",
            "trailer / music / craft": "The released material provides a concrete basis for discussing craft, marketing, and audience expectations.",
            "release / promotion": "The release information helps assess campaign timing and the competitive theatrical or streaming calendar.",
        }.get(category, "The story has enough verified context to support a focused Bollywood discussion without relying on speculation.")
        sentences.append(fallback)
    return " ".join(list(dict.fromkeys(sentences))[:2])


def _discussion_questions(category: str, temperature: str, matches: list[str]) -> list[str]:
    questions = {
        "fan culture / controversy": [
            "What event or claim triggered the audience reaction shown in the source metadata?",
            "Which parts of the debate are supported by reporting, and which come only from fandom activity?",
        ],
        "industry / business": [
            "What do the reported numbers or deal terms reveal about the underlying business strategy?",
            "Who gains leverage if this distribution, financing, or release decision succeeds?",
        ],
        "trailer / music / craft": [
            "Which craft choices are visible in the released material, separate from the campaign claims?",
            "What audience expectation is the marketing trying to establish before release?",
        ],
        "casting / production": [
            "Which casting or production details are confirmed by the available sources?",
            "How does the announced team fit the project, franchise, or current release strategy?",
        ],
        "awards / festivals": [
            "What does the recognition measure, and which work or performance is actually being recognised?",
            "How does this festival or award signal compare with the film's audience reception?",
        ],
        "release / promotion": [
            "How does the announced timing fit the theatrical or streaming calendar?",
            "What new information is present beyond the promotional announcement itself?",
        ],
    }.get(category, [
        "What is confirmed by the available source metadata?",
        "What consequence would make this story worth returning to on the podcast?",
    ])
    if matches:
        questions.append(f"How does this update change the existing watchlist context for {matches[0].split(':', 1)[-1].strip()}?")
    elif temperature == "speculative":
        questions.append("What additional source would be needed before treating the claim as established?")
    else:
        questions.append("Does the source activity show a sustained discussion or only a short-lived headline spike?")
    return questions[:3]


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


def score_story(story: Story, watchlist: dict | list[str] | None = None) -> Story:
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
    watchlist_matches, watchlist_bonus, watchlist_penalty = _structured_watchlist_signals(text, watchlist)
    signal_boost, routine_penalty, signal_reasons = _editorial_signal_adjustment(text)
    priority = _clamp(recency * 0.28 + consequence * 0.32 + confidence * 0.24 + engagement * 0.16 + watchlist_bonus + signal_boost - watchlist_penalty - routine_penalty)
    discussion = _clamp(consequence * 0.30 + controversy * 0.25 + engagement * 0.22 + confidence * 0.13 + priority * 0.10 + watchlist_bonus * 0.65 + signal_boost * 0.75 - watchlist_penalty * 0.7 - routine_penalty * 0.8)
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
    story.metadata["watchlist_matches"] = watchlist_matches
    story.metadata["editorial_signal_adjustment"] = round(signal_boost - routine_penalty, 1)
    reasons = [f"{category} consequence {consequence:.0f}/100"]
    if story.platform == "Google News":
        reasons.append(f"news confidence {confidence:.0f}/100")
    elif story.platform == "Reddit":
        reasons.append(f"audience engagement {engagement:.0f}/100")
    if recency >= 50:
        reasons.append(f"recency {recency:.0f}/100")
    if controversy >= 55:
        reasons.append(f"controversy {controversy:.0f}/100")
    if watchlist_matches:
        reasons.append(f"watchlist: {', '.join(watchlist_matches)}")
    if signal_reasons:
        reasons.append(f"editorial signals: {', '.join(signal_reasons)}")
    story.ranking_reasons = reasons
    story.why_khandaan_should_care = _why_khandaan_should_care(text, category, controversy, watchlist_matches)
    story.discussion_questions = _discussion_questions(category, temperature, watchlist_matches)
    story.source_summary = {
        "google_news": int(story.platform == "Google News"),
        "reddit": int(story.platform == "Reddit"),
        "listener": 0,
    }
    story.confidence_explanation = confidence_explanation(story)
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


def rank_stories(items: list[Story], watchlist: dict | list[str] | None = None) -> list[Story]:
    return sorted((score_story(item, watchlist) for item in items), key=lambda item: (item.discussion_score, item.priority_score), reverse=True)


TOPIC_STOPWORDS = {
    "a", "an", "and", "after", "bollywood", "box", "collection", "day", "film", "for",
    "from", "hindi", "in", "india", "indian", "live", "movie", "of", "office", "on",
    "or", "over", "says", "said", "the", "to", "update", "with",
}


def _near_duplicate_topic(left: Story, right: Story) -> bool:
    left_tokens = set(re.findall(r"[a-z0-9]+", left.title.lower())) - TOPIC_STOPWORDS
    right_tokens = set(re.findall(r"[a-z0-9]+", right.title.lower())) - TOPIC_STOPWORDS
    if not left_tokens or not right_tokens:
        return False
    shared = left_tokens & right_tokens
    return len(shared) >= 3 and len(shared) / min(len(left_tokens), len(right_tokens)) >= 0.25


def select_diverse_stories(
    items: list[Story],
    limit: int,
    *,
    max_per_google_keyword: int = 2,
    max_per_subreddit: int = 3,
) -> list[Story]:
    selected = []
    source_counts: dict[tuple[str, str], int] = {}
    for item in items:
        if any(_near_duplicate_topic(item, existing) for existing in selected):
            continue
        if item.platform == "Google News":
            key = (item.platform, str(item.metadata.get("keyword", "unknown")))
            cap = max_per_google_keyword
        elif item.platform == "Reddit":
            key = (item.platform, str(item.metadata.get("subreddit", "unknown")))
            cap = max_per_subreddit
        else:
            key = (item.platform, "all")
            cap = limit
        if source_counts.get(key, 0) >= cap:
            continue
        selected.append(item)
        source_counts[key] = source_counts.get(key, 0) + 1
        if len(selected) == limit:
            break
    return selected


def select_reel_opportunities(items: list[Story], limit: int = 5) -> list[Story]:
    active = [item for item in items if item.output_recommendation != "Ignore"]
    return sorted(
        active,
        key=lambda item: (
            item.output_recommendation in {"Reel", "Shorts"},
            item.topic_category == "trailer / music / craft",
            item.engagement_score,
            item.discussion_score,
        ),
        reverse=True,
    )[:limit]


def select_patreon_candidates(items: list[Story], limit: int = 5) -> list[Story]:
    active = [item for item in items if item.output_recommendation != "Ignore"]
    return sorted(
        active,
        key=lambda item: (
            item.output_recommendation == "Patreon Discussion",
            item.controversy_score * 0.55 + item.discussion_score * 0.45,
            item.confidence_score,
        ),
        reverse=True,
    )[:limit]


def rank_submissions(items: list[Submission]) -> list[Submission]:
    return sorted((score_submission(item) for item in items), key=lambda item: (item.discussion_score, item.priority_score), reverse=True)
