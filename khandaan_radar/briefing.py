from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Union

from .dashboard import Conversation, _story_clusters
from .models import Story, Submission
EditorialItem = Union[Story, Submission]


def _link(title: str, url: str) -> str:
    clean = " ".join(title.replace("[", "").replace("]", "").split()).strip()
    return f"[{clean}]({url})" if url else clean


def _title(item: EditorialItem) -> str:
    return item.title if isinstance(item, Story) else item.summary or "Listener story"


def _url(item: EditorialItem) -> str:
    return item.url if isinstance(item, Story) else item.story_link


def _source(item: EditorialItem) -> str:
    if isinstance(item, Story):
        if item.platform == "Reddit":
            return f"Reddit / r/{item.metadata.get('subreddit', 'unknown')}"
        return item.platform
    return f"Listener submission / {item.source_platform or 'unknown source'}"


def _editorial_label(item: EditorialItem) -> str:
    if item.output_recommendation == "Main Episode" and item.discussion_score >= 65:
        return "Essential"
    if item.output_recommendation != "Ignore" and item.discussion_score >= 45:
        return "Worth discussing"
    if item.discussion_score >= 30:
        return "Background"
    return "Skip"


def _bigger_trend(item: EditorialItem) -> str:
    trends = {
        "fan culture / controversy": "The way fandom turns taste, loyalty and disagreement into competing public identities.",
        "industry / business": "Bollywood's shifting economics: who holds leverage, where audiences spend, and how films now find value.",
        "trailer / music / craft": "The widening gap between a campaign's promise and the audience trust a film has actually earned.",
        "casting / production": "The star system's search for safety through franchises, familiar pairings and announcement-led momentum.",
        "release / promotion": "The battle for attention across a crowded theatrical and streaming calendar.",
        "general Bollywood": "Which parts of the publicity cycle survive once novelty and first reactions have worn off.",
    }
    return trends.get(item.topic_category, trends["general Bollywood"])


def _note(item: EditorialItem, *, listener_details: bool = False) -> list[str]:
    badges = " · ".join(f"`{badge}`" for badge in item.badges) or "`No badge`"
    if "Rumour" in item.badges or item.confidence_score < 40:
        confidence = "RUMOUR"
    elif item.confidence_score >= 70:
        confidence = "CONFIRMED SIGNAL"
    else:
        confidence = "VERIFY"
    why_it_matters = item.why_khandaan_should_care if isinstance(item, Story) else item.why_it_matters
    lines = [
        f"### {_link(_title(item), _url(item))}",
        f"**{_editorial_label(item)}**",
        "",
        f"**Why this matters:** {why_it_matters}",
        "",
        f"**What bigger trend does it represent?** {_bigger_trend(item)}",
        "",
        f"**Khandaan angle:** {item.khandaan_take}",
        "",
        f"**Is it worth our airtime?** {_editorial_label(item)}",
        "",
        "<details>",
        "<summary>Editorial Notes</summary>",
        "",
        f"- Signal: {item.trend_direction.upper()} · {item.age_label} · {confidence}",
        f"- Topic: {item.topic_category}",
        f"- Recommended treatment: {item.output_recommendation}",
        f"- Source badges: {badges}",
        f"- Editorial angle: {item.editorial_angle}",
        f"- Opening hook: {item.suggested_hook}",
        f"- Source signal: {_source(item)}",
    ]
    if isinstance(item, Story):
        sources = item.source_summary
        lines.extend([
            f"**Story lifecycle:** {item.lifecycle}",
            "",
            "**Discussion questions:**",
            *[f"- {question}" for question in item.discussion_questions],
            "",
            "**Related stories already in the dashboard:**",
            *(
                [
                    f"- {_link(related.get('title', 'Untitled story'), related.get('url', ''))} "
                    f"— {related.get('platform', 'Unknown source')}; {related.get('relationship', 'related metadata')}"
                    for related in item.related_stories
                ]
                or ["- No related dashboard story matched this story's metadata."]
            ),
            "",
            f"**Source summary:** Google News {sources['google_news']} · Reddit {sources['reddit']} · Listener {sources['listener']}",
            "",
            f"**Confidence explanation:** {item.confidence_explanation}",
            "",
        ])
    if isinstance(item, Story) and item.ranking_reasons:
        lines.extend([f"_Why ranked: {'; '.join(item.ranking_reasons)}._"])
    if listener_details and isinstance(item, Submission):
        flags = []
        if item.duplicate_count > 1:
            flags.append(f"submitted {item.duplicate_count} times")
        credit = ", ".join(item.submitters) if item.submitters else "anonymous / no public credit"
        lines.extend([f"_Listener signal: {', '.join(flags) if flags else 'single submission'}; credit: {credit}._"])
    return [*lines, "", "</details>", ""]


def _section(title: str, items: Iterable[EditorialItem], *, listener_details: bool = False, empty: str = "No strong candidate today.") -> list[str]:
    selected = list(items)
    lines = [title, ""]
    if not selected:
        return [*lines, f"_{empty}_", ""]
    for item in selected:
        lines.extend(_note(item, listener_details=listener_details))
    return lines


def _conversation_note(conversation: Conversation) -> list[str]:
    lead = conversation.lead
    if not isinstance(lead, Story):
        return _note(lead, listener_details=True)
    evidence = conversation.stories
    prompts = lead.discussion_questions[:2]
    return [
        f"### {conversation.title}",
        f"**{_editorial_label(lead)}**",
        "",
        f"**Why this matters:** {lead.why_khandaan_should_care}",
        "",
        f"**Khandaan angle:** {lead.khandaan_take}",
        "",
        "**Discussion prompts:**",
        *[f"- {prompt}" for prompt in prompts],
        "",
        f"**Supporting evidence:** {conversation.evidence_count}",
        *[f"- {_link(story.title, story.url)} — {story.platform}" for story in evidence],
        "",
        "<details>",
        "<summary>Editorial Notes</summary>",
        "",
        f"- Bigger trend: {_bigger_trend(lead)}",
        f"- Lifecycle: {lead.lifecycle}",
        f"- Topic: {lead.topic_category}",
        f"- Recommended treatment: {lead.output_recommendation}",
        f"- Confidence: {lead.confidence_explanation}",
        "",
        "</details>",
        "",
    ]


def _conversation_section(title: str, conversations: Iterable[Conversation], *, empty: str) -> list[str]:
    selected = list(conversations)
    lines = [title, ""]
    if not selected:
        return [*lines, f"_{empty}_", ""]
    for conversation in selected:
        lines.extend(_conversation_note(conversation))
    return lines


def _executive_summary(stories: list[Story], submissions: list[Submission]) -> list[str]:
    all_items: list[EditorialItem] = sorted([*stories, *submissions], key=lambda item: (item.discussion_score, item.priority_score), reverse=True)
    if not all_items:
        return ["No source material landed today. The useful editorial decision is to avoid manufacturing urgency."]
    lead = all_items[0]
    essential = sum(_editorial_label(item) == "Essential" for item in all_items)
    speculative = sum(item.audience_temperature == "speculative" for item in all_items)
    return [
        f"This fortnight's briefing contains **{len(all_items)} viable items**, including **{essential} essential discussion(s)**. "
        f"The lead conversation is **{_title(lead)}**: {_one_line(lead.editorial_angle)}",
        f"Audience read: **{speculative} speculative item(s)** need caveats before microphones are switched on. "
        "Prioritise stories with consequence, not merely volume; fandom noise is evidence of attention, not evidence of truth.",
    ]


def _one_line(text: str) -> str:
    return " ".join(text.split())


def render_briefing(path: Path, news: list[Story], reddit: list[Story], x_items: list[Story], submissions: list[Submission], editorial: dict | None = None) -> None:
    sort_key = lambda item: (item.discussion_score, item.priority_score)
    stories = sorted([*news, *reddit, *x_items], key=sort_key, reverse=True)
    submissions = sorted(submissions, key=sort_key, reverse=True)
    all_items: list[EditorialItem] = [*stories, *submissions]
    conversations = _story_clusters([item for item in stories if item.output_recommendation != "Ignore"])
    priorities = conversations[:5]
    bigger_picture = sorted(
        conversations[5:],
        key=lambda conversation: (
            "Industry Trend" in conversation.lead.badges,
            conversation.lead.discussion_score,
            conversation.lead.priority_score,
        ),
        reverse=True,
    )[:6]
    background = [item for item in stories if _editorial_label(item) in {"Background", "Skip"}]
    takes = [
        f"- **{_link(_title(item), _url(item))}:** “{item.khandaan_take}”"
        for item in stories[:3]
    ] or ["_No takes yet. Even we need a story before we can have an opinion._"]
    lines = [
        "# Khandaan Bollywood Radar",
        "",
        "_The conversations still worth having after the headlines._",
        "",
        f"_Editorial planning brief · {datetime.now().astimezone().strftime('%d %B %Y, %H:%M %Z')}_",
        "",
        "## 1. Editorial Note",
        "",
        *_executive_summary(stories, submissions),
        "",
        "## 2. Khandaan Take",
        "",
        *takes,
        "",
        *_conversation_section("## 3. Essential Conversations", priorities, empty="No conversation has earned a place in the briefing yet."),
        *_conversation_section("## 4. The Bigger Picture", bigger_picture, empty="No wider pattern has emerged from this fortnight's inputs."),
        *_section("## 5. From the Khandaan Audience", submissions, listener_details=True, empty="No listener submissions collected."),
        *_section("## 6. Background Reading", background, empty="Nothing has been parked as background reading."),
        "---",
        "",
        "**About Khandaan Bollywood Radar**",
        "",
        "Khandaan Bollywood Radar is an editorial briefing that turns news, fan discussions, Reddit conversations, X chatter and listener submissions into conversations worth returning to.",
        "",
        "[Produced by Khandaan: A Bollywood Podcast](https://www.youtube.com/@KhandaanPodcast)",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
