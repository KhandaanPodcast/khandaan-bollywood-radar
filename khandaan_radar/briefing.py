from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Union

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


def _note(item: EditorialItem, *, listener_details: bool = False) -> list[str]:
    badges = " · ".join(f"`{badge}`" for badge in item.badges) or "`No badge`"
    if "Rumour" in item.badges or item.confidence_score < 40:
        confidence = "RUMOUR"
    elif item.confidence_score >= 70:
        confidence = "CONFIRMED SIGNAL"
    else:
        confidence = "VERIFY"
    lines = [
        f"### {_link(_title(item), _url(item))}",
        f"**Discussion {item.discussion_score:.0f} · Priority {item.priority_score:.0f} · Controversy {item.controversy_score:.0f} · Engagement {item.engagement_score:.0f} · Confidence {item.confidence_score:.0f}**",
        f"**Trend {item.trend_direction.upper()} · {item.age_label} · Discussion {item.discussion_score / 10:.1f}/10 · Fan-war {item.controversy_score / 10:.1f}/10 · {confidence} {item.confidence_score / 10:.1f}/10**",
        "",
        f"**Badges:** {badges}  ",
        f"**Output:** {item.output_recommendation} · **Temperature:** {item.audience_temperature} · **Topic:** {item.topic_category}",
        "",
        f"**Khandaan Take:** {item.khandaan_take}",
        "",
        f"**Editorial note:** {item.editorial_angle}",
        "",
        f"**Opening hook:** {item.suggested_hook}",
        "",
        f"**Patron poll:** {item.suggested_patron_poll}",
        "",
        f"_Source signal: {_source(item)}._",
    ]
    if listener_details and isinstance(item, Submission):
        flags = []
        if item.duplicate_count > 1:
            flags.append(f"submitted {item.duplicate_count} times")
        if item.patreon_member:
            flags.append("includes a Patreon member")
        credit = ", ".join(item.submitters) if item.submitters else "anonymous / no public credit"
        lines.extend([f"_Listener signal: {', '.join(flags) if flags else 'single submission'}; credit: {credit}._"])
    return [*lines, ""]


def _section(title: str, items: Iterable[EditorialItem], *, listener_details: bool = False, empty: str = "No strong candidate today.") -> list[str]:
    selected = list(items)
    lines = [title, ""]
    if not selected:
        return [*lines, f"_{empty}_", ""]
    for item in selected:
        lines.extend(_note(item, listener_details=listener_details))
    return lines


def _executive_summary(stories: list[Story], submissions: list[Submission]) -> list[str]:
    all_items: list[EditorialItem] = sorted([*stories, *submissions], key=lambda item: (item.discussion_score, item.priority_score), reverse=True)
    if not all_items:
        return ["No source material landed today. The useful editorial decision is to avoid manufacturing urgency."]
    lead = all_items[0]
    hot = sum(item.discussion_score >= 60 for item in all_items)
    speculative = sum(item.audience_temperature == "speculative" for item in all_items)
    return [
        f"Today's board has **{len(all_items)} viable items**, with **{hot} scoring 60 or above for discussion**. "
        f"The lead candidate is **{_title(lead)}** at **{lead.discussion_score:.0f}/100 discussion**: {_one_line(lead.editorial_angle)}",
        f"Audience read: **{speculative} speculative item(s)** need caveats before microphones are switched on. "
        "Prioritise stories with consequence, not merely volume; fandom noise is evidence of attention, not evidence of truth.",
    ]


def _one_line(text: str) -> str:
    return " ".join(text.split())


def render_briefing(path: Path, news: list[Story], reddit: list[Story], x_items: list[Story], submissions: list[Submission], editorial: dict | None = None) -> None:
    sort_key = lambda item: (item.discussion_score, item.priority_score)
    stories = sorted([*news, *reddit, *x_items], key=sort_key, reverse=True)
    submissions = sorted(submissions, key=sort_key, reverse=True)
    all_items: list[EditorialItem] = sorted([*stories, *submissions], key=sort_key, reverse=True)
    patreon = [item for item in all_items if item.output_recommendation == "Patreon Discussion"][:1]
    reels = [item for item in all_items if item.output_recommendation in {"Reel", "Shorts"}][:4]
    podcast = [item for item in all_items if item.output_recommendation == "Main Episode"][:5]
    fan_war = [item for item in all_items if "Fan War" in item.badges][:4]
    industry = [item for item in all_items if "Industry Trend" in item.badges][:4]
    parked = [item for item in all_items if item.output_recommendation == "Ignore"]
    tonight = [item for item in all_items if item.output_recommendation != "Ignore"][:5]
    takes = [
        f"- **{_link(_title(item), _url(item))}:** “{item.khandaan_take}”"
        for item in all_items[:3]
    ] or ["_No takes yet. Even we need a story before we can have an opinion._"]
    tonight_lines = ["## 11. If We Recorded Tonight", ""]
    if tonight:
        for index, item in enumerate(tonight, start=1):
            tonight_lines.extend([
                f"{index}. **{_link(_title(item), _url(item))}** — Discussion **{item.discussion_score:.0f}/100** · {item.output_recommendation}",
                f"   {_one_line(item.khandaan_take)}",
                "",
            ])
    else:
        tonight_lines.extend(["_We would postpone the recording. No story currently earns the airtime._", ""])

    lines = [
        "# Khandaan Bollywood Radar",
        "",
        "_What Bollywood fans are actually talking about._",
        "",
        f"_Editorial planning brief · {datetime.now().astimezone().strftime('%d %B %Y, %H:%M %Z')}_",
        "",
        "## 1. Executive Summary",
        "",
        *_executive_summary(stories, submissions),
        "",
        "## 2. Khandaan Take",
        "",
        *takes,
        "",
        *_section("## 3. Top 3 Stories to Discuss", all_items[:3], empty="No story has earned the top table yet."),
        *_section("## 4. Best Patreon Discussion", patreon, empty="Nothing currently justifies putting the good biscuits behind the paywall."),
        *_section("## 5. Best Reel and Shorts Ideas", reels, empty="No item is visual or immediate enough for a short video today."),
        *_section("## 6. Main Episode Candidates", podcast, empty="No additional item has enough room for a proper main-episode conversation."),
        *_section("## 7. Fan War Watch", fan_war, empty="The fandom weather is unusually calm. Enjoy it responsibly."),
        *_section("## 8. Industry Trend Watch", industry, empty="No clear industry pattern has emerged from today's inputs."),
        *_section("## 9. Listener Submissions", submissions, listener_details=True, empty="No listener submissions collected."),
        *_section("## 10. Ignore", parked, empty="Nothing has been ignored; every collected item has a current assignment."),
        *tonight_lines,
        "---",
        "",
        "**About Khandaan Bollywood Radar**",
        "",
        "Khandaan Bollywood Radar combines news, fan discussions, Reddit conversations, X chatter and listener submissions to surface the Bollywood stories worth talking about.",
        "",
        "[Produced by Khandaan: A Bollywood Podcast](https://www.youtube.com/@KhandaanPodcast)",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
