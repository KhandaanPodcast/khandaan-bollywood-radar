from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from html import escape
import mimetypes
import os
from pathlib import Path
import re
from typing import Iterable, Union
from urllib.request import Request, urlopen

from .models import Story, Submission
DashboardItem = Union[Story, Submission]


@dataclass
class Conversation:
    title: str
    lead: DashboardItem
    stories: list[Story]

    @property
    def evidence_count(self) -> int:
        if not self.stories:
            return max(1, getattr(self.lead, "duplicate_count", 1))
        return sum(max(1, int(story.metadata.get("source_count", 1))) for story in self.stories)

BRAND_TITLE = "Khandaan Bollywood Radar"
BRAND_SUBTITLE = "The conversations still worth having"
SEO_DESCRIPTION = "A fortnightly editorial briefing on the Bollywood stories, debates and industry shifts still worth discussing."
SEO_KEYWORDS = "Bollywood news, Bollywood Reddit, Bollywood gossip, Bollywood box office, Hindi cinema, Bollywood podcast, Khandaan Podcast, Bollywood discussions, Bollywood trends"
ABOUT_COPY = "Khandaan Bollywood Radar is an editorial briefing that turns news, fan discussions, Reddit conversations, X chatter and listener submissions into conversations worth returning to."
PODCAST_URL = "https://www.youtube.com/@KhandaanPodcast"


@lru_cache(maxsize=64)
def _embedded_image(url: str, fetch_remote: bool) -> str:
    if not url:
        return ""
    if url.startswith("data:image/"):
        return url
    try:
        if url.startswith(("http://", "https://")):
            if not fetch_remote:
                return ""
            request = Request(url, headers={"User-Agent": "KhandaanBollywoodRadar/0.1"})
            with urlopen(request, timeout=8) as response:
                content_type = response.headers.get_content_type()
                data = response.read(5_000_001)
        else:
            image_path = Path(url).expanduser()
            if not image_path.is_file():
                return ""
            content_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
            data = image_path.read_bytes()
        if len(data) > 5_000_000 or not content_type.startswith("image/"):
            return ""
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{content_type};base64,{encoded}"
    except (OSError, ValueError):
        return ""


def _title(item: DashboardItem) -> str:
    return item.title if isinstance(item, Story) else item.summary or "Listener story"


def _url(item: DashboardItem) -> str:
    return item.url if isinstance(item, Story) else item.story_link


def _source(item: DashboardItem) -> str:
    if isinstance(item, Story):
        if item.platform == "Reddit":
            return f"Reddit / r/{item.metadata.get('subreddit', 'unknown')}"
        return item.platform
    return f"Listener / {item.source_platform or 'unknown source'}"


def _summary(item: DashboardItem) -> str:
    if isinstance(item, Submission):
        return item.why_it_matters
    return item.summary


def _editorial_label(item: DashboardItem) -> str:
    if item.output_recommendation == "Main Episode" and item.discussion_score >= 65:
        return "Essential"
    if item.output_recommendation != "Ignore" and item.discussion_score >= 45:
        return "Worth discussing"
    if item.discussion_score >= 30:
        return "Background"
    return "Skip"


def _watchlist_subject(story: Story) -> str:
    for match in story.metadata.get("watchlist_matches", []):
        subject = str(match).split(":", 1)[-1]
        subject = re.sub(r"\s*\(P[123]\)\s*$", "", subject, flags=re.IGNORECASE).strip()
        if subject:
            return subject
    return ""


def _short_subject(story: Story) -> str:
    watchlist_subject = _watchlist_subject(story)
    if watchlist_subject:
        return watchlist_subject
    title = re.split(r"\s(?:-|\||–|—)\s|:", story.title, maxsplit=1)[0]
    words = title.split()
    return " ".join(words[:9]).strip(" .,-") or "this story"


def _conversation_title(stories: list[Story]) -> str:
    lead = stories[0]
    subject = _short_subject(lead)
    templates = {
        "fan culture / controversy": f"What does {subject} reveal about how Bollywood fandom argues?",
        "industry / business": f"What does {subject} tell us about who holds power in Bollywood?",
        "trailer / music / craft": f"Has {subject} earned the audience's attention?",
        "casting / production": f"What is the strategy behind {subject}?",
        "release / promotion": f"Can {subject} cut through a crowded release calendar?",
        "general Bollywood": f"Is {subject} still worth talking about?",
    }
    return templates.get(lead.topic_category, templates["general Bollywood"])


def _story_clusters(stories: list[Story]) -> list[Conversation]:
    """Group the already-enriched story set without changing collection or scoring."""
    unassigned = list(stories)
    conversations: list[Conversation] = []
    while unassigned:
        lead = unassigned.pop(0)
        related_urls = {
            related.get("url", ""): related.get("relationship", "")
            for related in lead.related_stories
        }
        cluster = [lead]
        remaining: list[Story] = []
        for candidate in unassigned:
            candidate_urls = {
                related.get("url", ""): related.get("relationship", "")
                for related in candidate.related_stories
            }
            direct_reason = related_urls.get(candidate.url, "")
            reverse_reason = candidate_urls.get(lead.url, "")
            explicit_relation = any(
                reason.startswith("Same source URL")
                for reason in (direct_reason, reverse_reason)
            )
            is_related = bool(
                explicit_relation
                or (_watchlist_subject(lead) and _watchlist_subject(lead).lower() == _watchlist_subject(candidate).lower())
            )
            if is_related and len(cluster) < 5:
                cluster.append(candidate)
            else:
                remaining.append(candidate)
        unassigned = remaining
        conversations.append(Conversation(_conversation_title(cluster), lead, cluster))
    return conversations


def _submission_conversations(submissions: Iterable[Submission]) -> list[Conversation]:
    return [Conversation(_title(item), item, []) for item in submissions]


def _bigger_trend(item: DashboardItem) -> str:
    trends = {
        "fan culture / controversy": "The way fandom turns taste, loyalty and disagreement into competing public identities.",
        "industry / business": "Bollywood's shifting economics: who holds leverage, where audiences spend, and how films now find value.",
        "trailer / music / craft": "The widening gap between a campaign's promise and the audience trust a film has actually earned.",
        "casting / production": "The star system's search for safety through franchises, familiar pairings and announcement-led momentum.",
        "release / promotion": "The battle for attention across a crowded theatrical and streaming calendar.",
        "general Bollywood": "Which parts of the publicity cycle survive once novelty and first reactions have worn off.",
    }
    return trends.get(item.topic_category, trends["general Bollywood"])


def _confidence_label(item: DashboardItem) -> str:
    if "Rumour" in item.badges or item.confidence_score < 40:
        return "RUMOUR"
    if item.confidence_score >= 70:
        return "CONFIRMED SIGNAL"
    return "VERIFY"


def _conversation_prompts(item: DashboardItem) -> list[str]:
    if isinstance(item, Story):
        prompts = list(item.discussion_questions[:2])
    else:
        prompts = [item.editorial_angle, item.suggested_patron_poll]
    prompts.extend([item.suggested_hook, "What would change our mind about this conversation?"])
    return [prompt for prompt in prompts if prompt][:2]


def _evidence_descriptor(story: Story) -> str:
    text = f"{story.title} {story.summary}".lower()
    if "trailer" in text or "teaser" in text:
        return "Trailer coverage"
    if "cast" in text or "casting" in text:
        return "Casting discussion"
    if "release date" in text or "release calendar" in text:
        return "Release-date news"
    if "box office" in text or "advance booking" in text:
        return "Box-office reporting"
    if "streaming" in text or "ott" in text:
        return "Streaming coverage"
    return "Reported development"


def _copy_payload(conversation: Conversation) -> str:
    item = conversation.lead
    prompts = "\n".join(f"- {prompt}" for prompt in _conversation_prompts(item))
    sources = conversation.stories or ([item] if isinstance(item, Story) else [])
    source_lines = "\n".join(f"- {_title(source)}: {_url(source)}" for source in sources)
    if not source_lines and _url(item):
        source_lines = f"- {_title(item)}: {_url(item)}"
    why_it_matters = item.why_khandaan_should_care if isinstance(item, Story) else item.why_it_matters
    return (
        f"CONVERSATION NOTES\n\n{conversation.title}\n\nEditorial label: {_editorial_label(item)}\n\n"
        f"Why this matters: {why_it_matters}\n\nKhandaan angle: {item.khandaan_take}\n\n"
        f"Discussion prompts:\n{prompts}\n\nSupporting evidence: {conversation.evidence_count}\n{source_lines}"
    )


def _card(conversation: Conversation, card_id: str, *, self_contained: bool = False, fetch_images: bool = True) -> str:
    item = conversation.lead
    title = escape(conversation.title)
    editorial_label = _editorial_label(item)
    editorial_class = editorial_label.lower().replace(" ", "-")
    raw_image_url = _embedded_image(item.image_url, fetch_images) if self_contained else item.image_url
    image_url = escape(raw_image_url, quote=True)
    if image_url:
        media = f'<div class="story-media"><img src="{image_url}" alt="Supporting image for {title}" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentElement.classList.add(\'image-error\');this.remove()"><span class="image-fallback">KHANDAAN</span></div>'
    else:
        media = '<div class="story-media image-error"><span class="image-fallback">KHANDAAN</span></div>'
    copy_payload = f'<textarea id="{card_id}-notes" class="copy-payload" aria-hidden="true" tabindex="-1">{escape(_copy_payload(conversation))}</textarea>'
    listener_note = ""
    if isinstance(item, Submission):
        signals = [f"{item.duplicate_count} submission(s)"]
        if item.submitters:
            signals.append(f"credit: {', '.join(item.submitters)}")
        listener_note = f'<p class="listener-signal">{escape(" | ".join(signals))}</p>'
    prompts_html = "".join(f"<li>{escape(prompt)}</li>" for prompt in _conversation_prompts(item))
    if conversation.stories:
        evidence_html = "".join(
            f'<li><a href="{escape(story.url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(_evidence_descriptor(story))}<span>{escape(story.platform)} &nearr;</span></a></li>'
            for story in conversation.stories if story.url
        )
    else:
        url = _url(item)
        evidence_html = (
            f'<li><a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">Listener evidence<span>{escape(_source(item))} &nearr;</span></a></li>'
            if url else '<li class="no-related">No source link supplied.</li>'
        )
    if isinstance(item, Story):
        source_counts = item.source_summary
        intelligence_html = f"""
      <p><strong>Story lifecycle</strong>{escape(item.lifecycle)}</p>
      <p><strong>Why this matters</strong>{escape(item.why_khandaan_should_care)}</p>
      <p><strong>Bigger trend</strong>{escape(_bigger_trend(item))}</p>
      <div class="briefing-list"><strong>Clustered articles</strong><ul>{evidence_html}</ul></div>
      <p><strong>Source summary</strong>Google News {source_counts['google_news']} &middot; Reddit {source_counts['reddit']} &middot; Listener {source_counts['listener']}</p>
      <p><strong>Confidence explanation</strong>{escape(item.confidence_explanation)}</p>"""
        why_it_matters = item.why_khandaan_should_care or _summary(item)
    else:
        intelligence_html = ""
        why_it_matters = item.why_it_matters
    return f"""
<article class="story-card">
  <div class="media-wrap">{media}</div>
  <div class="story-copy">
    <div class="card-kicker"><p class="eyebrow">EDITORIAL CONVERSATION</p><span class="editorial-label {editorial_class}">{editorial_label}</span></div>
    <h3>{title}</h3>
  </div>
  <div class="editorial-brief">
    <div><p>Why this matters</p><span>{escape(why_it_matters)}</span></div>
    <div><p>Khandaan angle</p><span>{escape(item.khandaan_take)}</span></div>
    <div class="discussion-prompts"><p>Discussion prompts</p><ol>{prompts_html}</ol></div>
  </div>
{listener_note}
  <div class="evidence"><div class="evidence-heading"><p>Supporting evidence</p><span>{conversation.evidence_count}</span></div><ul>{evidence_html}</ul></div>
  <details>
    <summary>Editorial Notes</summary>
    <div class="details-body">
{intelligence_html}
      <p><strong>Signal</strong>{escape(item.trend_direction.title())} &middot; {escape(item.age_label)} &middot; {_confidence_label(item)}</p>
      <p><strong>Topic</strong>{escape(item.topic_category)}</p>
      <p><strong>Recommended treatment</strong>{escape(item.output_recommendation)}</p>
      <p><strong>Editorial angle</strong>{escape(item.editorial_angle)}</p>
      <p><strong>Suggested hook</strong>{escape(item.suggested_hook)}</p>
      <p><strong>Source badges</strong>{escape(", ".join(item.badges) or "None")}</p>
      <div class="copy-actions"><button type="button" data-copy-target="{card_id}-notes">Copy conversation notes</button></div>
    </div>
  </details>
  {copy_payload}
</article>"""


def _section(section_id: str, title: str, kicker: str, items: Iterable[Conversation], *, empty: str = "Nothing here today.", self_contained: bool = False, fetch_images: bool = True) -> str:
    selected = list(items)
    cards = "".join(
        _card(conversation, f"{section_id}-{index}", self_contained=self_contained, fetch_images=fetch_images)
        for index, conversation in enumerate(selected, start=1)
    )
    if not selected:
        cards = f'<div class="empty-state">{escape(empty)}</div>'
    return f"""
<section id="{section_id}" class="dashboard-section">
  <div class="section-heading"><div><p>{escape(kicker)}</p><h2>{escape(title)}</h2></div></div>
  <div class="card-grid">{cards}</div>
</section>"""


def render_dashboard(
    path: Path,
    news: list[Story],
    reddit: list[Story],
    x_items: list[Story],
    submissions: list[Submission],
    markdown_path: Path | None = None,
    *,
    self_contained: bool = False,
    fetch_images: bool = True,
    public_url: str = "",
) -> None:
    sort_key = lambda item: (item.discussion_score, item.priority_score)
    story_items: list[Story] = sorted([*news, *reddit, *x_items], key=sort_key, reverse=True)
    active = [item for item in story_items if item.output_recommendation != "Ignore"]
    conversations = _story_clusters(active)
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
    recent_submissions = sorted(
        submissions,
        key=lambda item: (
            item.submitted_at is not None,
            item.submitted_at.timestamp() if item.submitted_at else 0,
        ),
        reverse=True,
    )[:4]
    listener_conversations = _submission_conversations(recent_submissions)
    generated = datetime.now().astimezone().strftime("%d %B %Y &middot; %H:%M %Z")
    markdown_path = markdown_path or path.with_name("briefing.md")
    markdown_href = escape(os.path.relpath(markdown_path, path.parent), quote=True)
    safe_public_url = escape(public_url.strip(), quote=True)
    canonical = f'<link rel="canonical" href="{safe_public_url}"><meta property="og:url" content="{safe_public_url}">' if safe_public_url else ""
    footer_export = "Static share edition: upload this one HTML file as-is." if self_contained else f'<a href="{markdown_href}">Open Markdown export</a>.'
    sections = "".join([
        _section("start-here", "Essential Conversations", "START HERE", priorities, empty="No conversation has earned a place in the briefing yet.", self_contained=self_contained, fetch_images=fetch_images),
        _section("bigger-picture", "The Bigger Picture", "PATTERNS, NOT PULSES", bigger_picture, empty="No wider pattern has emerged from this fortnight's inputs.", self_contained=self_contained, fetch_images=fetch_images),
        _section("listener-submissions", "From the Khandaan Audience", "THE LISTENER'S DESK", listener_conversations, empty="No listener submissions collected.", self_contained=self_contained, fetch_images=fetch_images),
    ])
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <meta name="description" content="{escape(SEO_DESCRIPTION, quote=True)}">
  <meta name="keywords" content="{escape(SEO_KEYWORDS, quote=True)}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{escape(BRAND_TITLE, quote=True)}">
  <meta property="og:description" content="{escape(SEO_DESCRIPTION, quote=True)}">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="{escape(BRAND_TITLE, quote=True)}">
  <meta name="twitter:description" content="{escape(SEO_DESCRIPTION, quote=True)}">
  {canonical}
  <title>{escape(BRAND_TITLE)}</title>
  <style>
    :root {{ --ink:#09090a; --panel:#151517; --panel-2:#1d1d20; --line:#333338; --text:#f8f6ef; --muted:#aaa7a0; --yellow:#ffe000; --pink:#ff3f8e; --green:#78e2a7; }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; }}
    body {{ margin:0; background:var(--ink); color:var(--text); font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; line-height:1.5; }}
    body::before {{ content:""; position:fixed; inset:0; pointer-events:none; opacity:.2; background:radial-gradient(circle at 10% 0,rgba(255,63,142,.13),transparent 30%),radial-gradient(circle at 90% 8%,rgba(255,224,0,.1),transparent 28%); }}
    a {{ color:inherit; text-decoration:none; }} a:hover {{ color:var(--yellow); }}
    .shell {{ width:min(100% - 24px,1160px); margin:auto; position:relative; }}
    header {{ padding:20px 0 25px; border-bottom:1px solid var(--line); }}
    .brand-line {{ display:flex; align-items:flex-start; flex-direction:column; gap:22px; }}
    .brand-actions {{ display:flex; width:100%; align-items:center; gap:8px; }}
    .share-button,.download-button {{ flex:1; min-height:40px; padding:9px 12px; border:1px solid var(--line); border-radius:4px; background:var(--panel); color:var(--text); font:inherit; font-size:.66rem; font-weight:900; letter-spacing:.06em; text-transform:uppercase; cursor:pointer; }}
    .share-button {{ color:var(--ink); border-color:var(--yellow); background:var(--yellow); }} .share-button:hover,.download-button:hover {{ border-color:var(--pink); background:var(--pink); color:white; }}
    .share-status {{ min-height:1.4em; margin:8px 0 0; color:var(--muted); font-size:.7rem; }}
    .brand-lockup {{ display:flex; align-items:center; gap:13px; }}
    .wordmark {{ display:flex; flex-direction:column; align-items:flex-start; line-height:.88; font-weight:950; }}
    .wordmark-khandaan {{ color:var(--text); font-size:.86rem; letter-spacing:.22em; }}
    .wordmark-radar {{ position:relative; margin-top:7px; color:var(--yellow); font-size:clamp(1.42rem,7vw,2.3rem); letter-spacing:-.04em; }}
    .wordmark-radar em {{ color:var(--pink); font-style:normal; }} .wordmark-radar::after {{ content:""; position:absolute; left:0; right:0; bottom:-9px; height:3px; background:linear-gradient(90deg,var(--yellow) 0 72%,var(--pink) 72%); }}
    .brand-dot {{ width:13px; height:13px; border-radius:50%; background:var(--pink); box-shadow:18px 0 0 var(--yellow); margin-right:18px; }}
    .date {{ margin-top:23px; color:var(--muted); font-size:.68rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; }}
    .hero {{ padding:56px 0 18px; display:block; }}
    .hero-label {{ margin:0; color:var(--pink); font-size:.7rem; font-weight:900; letter-spacing:.18em; text-transform:uppercase; }}
    h1 {{ margin:.5rem 0 1rem; max-width:880px; font-family:Georgia,"Times New Roman",serif; font-size:clamp(2.55rem,11vw,5.6rem); font-weight:700; line-height:.94; letter-spacing:-.055em; }}
    h1 em {{ color:var(--yellow); font-style:normal; }}
    .hero-copy {{ margin:0; color:#d0cdc6; max-width:720px; font-family:Georgia,"Times New Roman",serif; font-size:1.08rem; }}
    .quick-nav {{ position:sticky; top:0; z-index:20; padding:10px 0; background:rgba(9,9,10,.94); backdrop-filter:blur(16px); border-bottom:1px solid var(--line); }}
    .quick-nav .shell {{ display:flex; gap:8px; overflow:auto; }}
    .quick-nav a {{ white-space:nowrap; padding:7px 10px; color:var(--muted); border-left:2px solid var(--line); font-size:.65rem; font-weight:900; text-transform:uppercase; letter-spacing:.08em; }}
    .quick-nav a:hover {{ color:var(--ink); border-color:var(--yellow); background:var(--yellow); }}
    main {{ padding-bottom:60px; }}
    .dashboard-section {{ padding:64px 0 12px; scroll-margin-top:58px; }}
    .section-heading {{ display:flex; justify-content:space-between; align-items:end; margin-bottom:24px; padding-bottom:14px; border-bottom:3px solid var(--text); }}
    .section-heading p {{ margin:0 0 5px; color:var(--pink); font-size:.72rem; font-weight:900; letter-spacing:.15em; }}
    h2 {{ margin:0; font-family:Georgia,"Times New Roman",serif; font-size:clamp(1.75rem,8vw,3.1rem); line-height:1; letter-spacing:-.045em; }}
    .card-grid {{ display:grid; grid-template-columns:1fr; gap:22px; }}
    .story-card {{ display:flex; flex-direction:column; gap:18px; min-width:0; padding:22px; overflow:hidden; background:linear-gradient(150deg,var(--panel),#101011); border-top:1px solid #58585f; box-shadow:0 15px 45px rgba(0,0,0,.16); }}
    .story-card:hover {{ border-top-color:var(--yellow); transition:.18s ease; }}
    .media-wrap {{ position:relative; margin:-22px -22px 0; }}
    .story-media {{ position:relative; height:210px; overflow:hidden; background:radial-gradient(circle at 22% 30%,rgba(255,61,141,.5),transparent 32%),radial-gradient(circle at 78% 70%,rgba(255,230,0,.36),transparent 32%),#242428; }}
    .story-media img {{ width:100%; height:100%; display:block; object-fit:cover; }}
    .image-fallback {{ display:none; position:absolute; inset:0; place-items:center; color:rgba(255,255,255,.13); font-size:clamp(2rem,5vw,4.7rem); font-weight:950; letter-spacing:-.07em; transform:rotate(-7deg); }}
    .story-media.image-error .image-fallback {{ display:grid; }}
    .card-kicker {{ display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:8px; }}
    .editorial-label {{ padding:5px 8px; border:1px solid var(--line); color:var(--muted); font-size:.57rem; font-weight:950; letter-spacing:.08em; text-transform:uppercase; white-space:nowrap; }}
    .editorial-label.essential {{ color:var(--ink); border-color:var(--yellow); background:var(--yellow); }}
    .editorial-label.worth-discussing {{ color:var(--green); border-color:rgba(120,226,167,.55); }}
    .editorial-label.background {{ color:var(--text); border-color:#6b6b72; }} .editorial-label.skip {{ color:var(--pink); border-color:rgba(255,63,142,.5); }}
    .eyebrow {{ margin:0 0 5px; color:var(--muted); font-size:.68rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }}
    .eyebrow span {{ color:var(--pink); }} h3 {{ margin:0; font-family:Georgia,"Times New Roman",serif; font-size:clamp(1.28rem,6vw,1.72rem); line-height:1.08; letter-spacing:-.025em; }}
    .story-dek {{ margin:10px 0 0; color:#c4c0b8; font-size:.86rem; line-height:1.5; }}
    .editorial-brief {{ display:grid; gap:0; border-top:1px solid var(--line); }}
    .editorial-brief>div {{ display:grid; gap:5px; padding:13px 0; border-bottom:1px solid var(--line); }}
    .editorial-brief p {{ margin:0; color:var(--pink); font-size:.58rem; font-weight:950; letter-spacing:.1em; text-transform:uppercase; }}
    .editorial-brief span {{ color:#e6e2da; font-family:Georgia,"Times New Roman",serif; font-size:.93rem; line-height:1.5; }}
    .discussion-prompts ol {{ margin:3px 0 0; padding-left:20px; color:#e6e2da; font-family:Georgia,"Times New Roman",serif; font-size:.93rem; }} .discussion-prompts li+li {{ margin-top:7px; }}
    .listener-signal {{ margin:0; color:var(--muted); font-size:.72rem; }}
    .evidence {{ border:1px solid var(--line); background:rgba(29,29,32,.55); }} .evidence-heading {{ display:flex; align-items:center; justify-content:space-between; gap:12px; padding:10px 12px; border-bottom:1px solid var(--line); }} .evidence-heading p {{ margin:0; color:var(--text); font-size:.61rem; font-weight:950; letter-spacing:.08em; text-transform:uppercase; }} .evidence-heading span {{ display:grid; place-items:center; min-width:24px; height:24px; background:var(--yellow); color:var(--ink); font-size:.72rem; font-weight:950; }} .evidence ul {{ list-style:none; margin:0; padding:0; }} .evidence li+li {{ border-top:1px solid var(--line); }} .evidence a {{ display:flex; align-items:center; justify-content:space-between; gap:12px; padding:10px 12px; color:#e9e5dd; font-size:.72rem; }} .evidence a:hover {{ background:var(--panel-2); }} .evidence a span {{ color:var(--muted); font-size:.62rem; white-space:nowrap; }}
    .source-link,.copy-actions button {{ display:inline-flex; align-items:center; justify-content:center; min-height:34px; padding:8px 10px; border:1px solid var(--line); background:transparent; color:var(--text); font:inherit; font-size:.61rem; font-weight:850; letter-spacing:.03em; cursor:pointer; }}
    .source-link {{ border-color:rgba(255,230,0,.55); color:var(--yellow); }} .source-link.disabled {{ color:var(--muted); border-color:var(--line); cursor:default; }}
    .copy-actions {{ display:flex; flex-wrap:wrap; gap:6px; }} .copy-actions button:hover,.copy-actions button.copied {{ color:var(--ink); border-color:var(--yellow); background:var(--yellow); }}
    .copy-payload {{ position:fixed; left:-10000px; top:-10000px; width:1px; height:1px; opacity:0; pointer-events:none; }}
    details {{ margin-top:auto; border-top:1px solid var(--line); padding-top:14px; }} summary {{ cursor:pointer; color:var(--muted); font-size:.68rem; font-weight:850; text-transform:uppercase; letter-spacing:.08em; }} summary:hover {{ color:var(--yellow); }}
    .details-body {{ padding-top:8px; color:var(--muted); font-size:.82rem; }} .details-body p {{ margin:12px 0 0; }} .details-body strong {{ display:block; color:var(--text); font-size:.64rem; text-transform:uppercase; letter-spacing:.07em; }} .details-body .copy-actions {{ margin-top:16px; }}
    .briefing-list {{ margin-top:12px; }} .briefing-list ol,.briefing-list ul {{ margin:7px 0 0; padding-left:20px; }} .briefing-list li {{ margin:5px 0; }} .briefing-list li span {{ display:block; color:#85827d; font-size:.72rem; }} .briefing-list a {{ color:var(--yellow); }} .briefing-list .no-related {{ list-style:none; margin-left:-20px; }}
    .empty-state {{ grid-column:1/-1; padding:36px; color:var(--muted); border:1px dashed var(--line); text-align:center; }}
    footer {{ padding:38px 0 55px; color:var(--muted); border-top:1px solid var(--line); font-size:.8rem; }} footer a {{ color:var(--yellow); font-weight:850; }}
    .footer-grid {{ display:grid; grid-template-columns:minmax(0,1.6fr) minmax(240px,.6fr); gap:30px; align-items:end; }} .footer-about strong {{ display:block; margin-bottom:7px; color:var(--pink); font-size:.66rem; letter-spacing:.12em; }} .footer-about p {{ margin:0; max-width:820px; color:#d4d0c8; font-size:.9rem; }} .footer-meta {{ display:flex; flex-direction:column; align-items:flex-end; gap:8px; text-align:right; }} .producer-link {{ font-size:.72rem; }}
    @media (max-width:559px) {{ h1,h3 {{ overflow-wrap:anywhere; }} .card-kicker {{ align-items:flex-start; flex-direction:column; }} .copy-actions {{ align-items:stretch; flex-direction:column; width:100%; }} .source-link,.copy-actions button {{ width:100%; }} .footer-grid {{ grid-template-columns:1fr; }} .footer-meta {{ align-items:flex-start; text-align:left; }} }}
    @media (min-width:700px) {{ .shell {{ width:min(100% - 48px,1160px); }} header {{ padding-top:30px; }} .brand-line {{ align-items:center; flex-direction:row; justify-content:space-between; }} .brand-actions {{ width:auto; }} .share-button,.download-button {{ flex:none; }} .share-status {{ text-align:right; }} .card-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .story-media {{ height:250px; }} }}
    @media (min-width:1040px) {{ #start-here .card-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} #start-here .story-card:first-child {{ grid-column:1/-1; display:grid; grid-template-columns:minmax(0,1.05fr) minmax(0,1fr); column-gap:32px; }} #start-here .story-card:first-child .media-wrap {{ grid-row:1/7; margin:-22px 0 -22px -22px; }} #start-here .story-card:first-child .story-media {{ height:100%; min-height:600px; }} #bigger-picture .card-grid,#listener-submissions .card-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .dashboard-section {{ padding-top:76px; }} }}
    @media print {{ .quick-nav,details {{ display:none; }} body {{ background:white; color:black; }} .story-card,.stat {{ break-inside:avoid; box-shadow:none; }} }}
  </style>
</head>
<body data-public-url="{safe_public_url}">
  <header><div class="shell">
    <div class="brand-line"><div class="brand-lockup"><span class="brand-dot"></span><div class="wordmark" aria-label="KHANDAAN BOLLYWOOD RADAR"><span class="wordmark-khandaan">KHANDAAN</span><span class="wordmark-radar">BOLLYWOOD <em>RADAR</em></span></div></div><div><div class="brand-actions"><button class="share-button" type="button" id="share-dashboard">Share dashboard</button><button class="download-button" type="button" id="download-dashboard">Download HTML</button></div><p class="share-status" id="share-status" aria-live="polite"></p></div></div>
    <div class="date">{generated}</div>
    <div class="hero"><p class="hero-label">THE FORTNIGHT IN BOLLYWOOD</p><h1>The conversations still worth having <em>after the headlines</em></h1><p class="hero-copy">A considered editorial briefing on what matters, what it reveals, and what deserves Khandaan's airtime.</p></div>
  </div></header>
  <nav class="quick-nav" aria-label="Editorial desks"><div class="shell"><a href="#start-here">Essential Conversations</a><a href="#bigger-picture">The Bigger Picture</a><a href="#listener-submissions">From the Audience</a></div></nav>
  <main class="shell">{sections}</main>
  <footer><div class="shell footer-grid"><div class="footer-about"><strong>ABOUT KHANDAAN BOLLYWOOD RADAR</strong><p>{escape(ABOUT_COPY)}</p></div><div class="footer-meta"><a class="producer-link" href="{PODCAST_URL}" target="_blank" rel="noopener noreferrer">Produced by Khandaan: A Bollywood Podcast</a><span>{footer_export}</span></div></div></footer>
  <script>
    function fallbackCopy(text) {{
      const area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      const copied = document.execCommand('copy');
      area.remove();
      return copied;
    }}
    async function copyPlanning(button) {{
      const payload = document.getElementById(button.dataset.copyTarget);
      if (!payload) return;
      let copied = false;
      try {{
        if (navigator.clipboard && window.isSecureContext) {{
          await navigator.clipboard.writeText(payload.value);
          copied = true;
        }} else {{
          copied = fallbackCopy(payload.value);
        }}
      }} catch (error) {{
        copied = fallbackCopy(payload.value);
      }}
      const original = button.textContent;
      button.textContent = copied ? 'Copied!' : 'Select and copy';
      button.classList.toggle('copied', copied);
      window.setTimeout(() => {{ button.textContent = original; button.classList.remove('copied'); }}, 1600);
    }}
    document.addEventListener('click', (event) => {{
      const button = event.target.closest('[data-copy-target]');
      if (button) copyPlanning(button);
    }});
    function downloadableHtml() {{
      return '<!doctype html>\\n' + document.documentElement.outerHTML;
    }}
    function downloadDashboard() {{
      const blob = new Blob([downloadableHtml()], {{ type: 'text/html' }});
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'khandaan-dashboard.html';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(link.href);
      document.getElementById('share-status').textContent = 'Share-ready HTML downloaded.';
    }}
    async function shareDashboard() {{
      const status = document.getElementById('share-status');
      const publicUrl = document.body.dataset.publicUrl;
      const data = {{ title: '{BRAND_TITLE}', text: '{BRAND_SUBTITLE}' }};
      if (publicUrl) data.url = publicUrl;
      try {{
        if (navigator.share && publicUrl) {{
          await navigator.share(data);
          status.textContent = 'Dashboard shared.';
        }} else if (publicUrl) {{
          const copied = navigator.clipboard && window.isSecureContext ? (await navigator.clipboard.writeText(publicUrl), true) : fallbackCopy(publicUrl);
          status.textContent = copied ? 'Public link copied.' : 'Public link: ' + publicUrl;
        }} else {{
          downloadDashboard();
          status.textContent = 'No public URL configured; share-ready HTML downloaded.';
        }}
      }} catch (error) {{
        if (error && error.name === 'AbortError') return;
        status.textContent = publicUrl ? 'Share this link: ' + publicUrl : 'Use Download HTML to share this file.';
      }}
    }}
    document.getElementById('share-dashboard').addEventListener('click', shareDashboard);
    document.getElementById('download-dashboard').addEventListener('click', downloadDashboard);
  </script>
</body>
</html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
