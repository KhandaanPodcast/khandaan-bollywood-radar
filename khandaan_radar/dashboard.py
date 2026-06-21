from __future__ import annotations

import base64
from datetime import datetime
from functools import lru_cache
from html import escape
import mimetypes
import os
from pathlib import Path
from typing import Iterable, Union
from urllib.request import Request, urlopen

from .models import Story, Submission


DashboardItem = Union[Story, Submission]

BRAND_TITLE = "Khandaan Bollywood Radar"
BRAND_SUBTITLE = "What Bollywood fans are talking about this week"
SEO_DESCRIPTION = "The stories, debates, fan wars and industry shifts shaping Bollywood this week. Powered by news, Reddit discussions, X conversations and audience submissions."
SEO_KEYWORDS = "Bollywood news, Bollywood Reddit, Bollywood gossip, Bollywood box office, Hindi cinema, Bollywood podcast, Khandaan Podcast, Bollywood discussions, Bollywood trends"
ABOUT_COPY = "Khandaan Bollywood Radar combines news, fan discussions, Reddit conversations, X chatter and listener submissions to surface the Bollywood stories worth talking about."
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


def _dashboard_badges(item: DashboardItem) -> list[str]:
    badges = []
    if item.discussion_score >= 60:
        badges.append("HIGH INTEREST")
    if "Fan War" in item.badges:
        badges.append("FAN WAR")
    if (isinstance(item, Submission) and item.patreon_member) or item.output_recommendation == "Patreon Discussion":
        badges.append("PATREON")
    if isinstance(item, Story) and item.recency_hours <= 12 and item.confidence_score >= 60:
        badges.append("BREAKING")
    if item.output_recommendation in {"Reel", "Shorts"}:
        badges.append("REEL IDEA")
    if item.output_recommendation == "Main Episode":
        badges.append("PODCAST")
    return badges


def _badge(label: str) -> str:
    css_name = label.lower().replace(" ", "-")
    return f'<span class="badge badge-{css_name}">{escape(label)}</span>'


def _confidence_label(item: DashboardItem) -> str:
    if "Rumour" in item.badges or item.confidence_score < 40:
        return "RUMOUR"
    if item.confidence_score >= 70:
        return "CONFIRMED SIGNAL"
    return "VERIFY"


def _copy_payloads(item: DashboardItem) -> tuple[str, str, str]:
    title = _title(item)
    source = _url(item) or "No source link"
    podcast = (
        f"PODCAST NOTES\n\n{title}\n\nDiscussion: {item.discussion_score / 10:.1f}/10\n"
        f"Confidence: {_confidence_label(item)} ({item.confidence_score / 10:.1f}/10)\n\n"
        f"Khandaan Take: {item.khandaan_take}\n\nEditorial angle: {item.editorial_angle}\n\n"
        f"Opening hook: {item.suggested_hook}\n\nSource: {source}"
    )
    reel = (
        f"REEL IDEA\n\nHook: {item.suggested_hook}\n\nStory: {title}\n\n"
        f"Talking point: {item.khandaan_take}\n\nOn-screen question: {item.suggested_patron_poll}\n\nSource: {source}"
    )
    patreon = (
        f"PATREON POST\n\n{title}\n\n{item.khandaan_take}\n\n"
        f"What we want to discuss: {item.editorial_angle}\n\nPatron question: {item.suggested_patron_poll}\n\nSource: {source}"
    )
    return podcast, reel, patreon


def _card(item: DashboardItem, card_id: str, *, rank: int | None = None, self_contained: bool = False, fetch_images: bool = True) -> str:
    title = escape(_title(item))
    url = escape(_url(item), quote=True)
    linked_title = f'<a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a>' if url else title
    badges = "".join(_badge(label) for label in _dashboard_badges(item))
    if not badges:
        badges = '<span class="badge badge-watch">WATCH</span>'
    rank_html = f'<span class="rank">{rank}</span>' if rank is not None else ""
    raw_image_url = _embedded_image(item.image_url, fetch_images) if self_contained else item.image_url
    image_url = escape(raw_image_url, quote=True)
    if image_url:
        media = f'<div class="story-media"><img src="{image_url}" alt="Poster or story image for {title}" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentElement.classList.add(\'image-error\');this.remove()"><span class="image-fallback">KHANDAAN</span></div>'
    else:
        media = '<div class="story-media image-error"><span class="image-fallback">KHANDAAN</span></div>'
    trend = item.trend_direction if item.trend_direction in {"up", "down", "new"} else "new"
    trend_arrow = {"up": "&uarr;", "down": "&darr;", "new": "&#10022;"}[trend]
    source_link = f'<a class="source-link" href="{url}" target="_blank" rel="noopener noreferrer">Open source <span>&nearr;</span></a>' if url else '<span class="source-link disabled">No source link</span>'
    podcast_copy, reel_copy, patreon_copy = _copy_payloads(item)
    copy_payloads = "".join([
        f'<textarea id="{card_id}-podcast" class="copy-payload" aria-hidden="true">{escape(podcast_copy)}</textarea>',
        f'<textarea id="{card_id}-reel" class="copy-payload" aria-hidden="true">{escape(reel_copy)}</textarea>',
        f'<textarea id="{card_id}-patreon" class="copy-payload" aria-hidden="true">{escape(patreon_copy)}</textarea>',
    ])
    summary = escape(_summary(item))
    summary_html = f'<p class="story-dek">{summary}</p>' if summary else ""
    listener_note = ""
    if isinstance(item, Submission):
        signals = [f"{item.duplicate_count} submission(s)"]
        if item.patreon_member:
            signals.append("Patreon member")
        if item.submitters:
            signals.append(f"credit: {', '.join(item.submitters)}")
        listener_note = f'<p class="listener-signal">{escape(" | ".join(signals))}</p>'
    return f"""
<article class="story-card">
  <div class="media-wrap">{media}<div class="story-status"><span class="trend trend-{trend}">{trend_arrow} {trend.upper()}</span><span class="age">{escape(item.age_label)}</span></div></div>
  <div class="card-top">{rank_html}<div class="badge-row">{badges}</div></div>
  <div class="story-copy">
    <p class="eyebrow">{escape(_source(item))} <span>&middot;</span> {escape(item.topic_category)}</p>
    <h3>{linked_title}</h3>
{summary_html}
  </div>
  <div class="editorial-meta">
    <div><b>{item.discussion_score:.0f}</b><span>Discussion</span></div>
    <div><b>{item.controversy_score:.0f}</b><span>Heat</span></div>
    <div><b>{item.confidence_score:.0f}</b><span>{_confidence_label(item)}</span></div>
    <strong>{escape(item.output_recommendation)}</strong>
  </div>
  <blockquote><span>THE KHANDAAN ANGLE</span>{escape(item.khandaan_take)}</blockquote>
{listener_note}
  <div class="card-actions">{source_link}<div class="copy-actions"><button type="button" data-copy-target="{card_id}-podcast">Copy podcast notes</button><button type="button" data-copy-target="{card_id}-reel">Copy reel idea</button><button type="button" data-copy-target="{card_id}-patreon">Copy Patreon post</button></div></div>
  {copy_payloads}
  <details>
    <summary>Open planning notes</summary>
    <div class="details-body">
      <p><strong>Editorial angle</strong>{escape(item.editorial_angle)}</p>
      <p><strong>Suggested hook</strong>{escape(item.suggested_hook)}</p>
      <p><strong>Patron poll</strong>{escape(item.suggested_patron_poll)}</p>
      <p><strong>Source badges</strong>{escape(", ".join(item.badges) or "None")}</p>
    </div>
  </details>
</article>"""


def _section(section_id: str, title: str, kicker: str, items: Iterable[DashboardItem], *, ranked: bool = False, empty: str = "Nothing here today.", self_contained: bool = False, fetch_images: bool = True) -> str:
    selected = list(items)
    cards = "".join(
        _card(item, f"{section_id}-{index}", rank=index if ranked else None, self_contained=self_contained, fetch_images=fetch_images)
        for index, item in enumerate(selected, start=1)
    )
    if not selected:
        cards = f'<div class="empty-state">{escape(empty)}</div>'
    return f"""
<section id="{section_id}" class="dashboard-section">
  <div class="section-heading"><div><p>{escape(kicker)}</p><h2>{escape(title)}</h2></div><span>{len(selected):02d}</span></div>
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
    all_items: list[DashboardItem] = sorted([*news, *reddit, *x_items, *submissions], key=sort_key, reverse=True)
    active = [item for item in all_items if item.output_recommendation != "Ignore"]
    tonight = active[:5]
    trending = active[:8]
    fan_war = sorted(active, key=lambda item: (item.controversy_score, item.discussion_score), reverse=True)[:5]
    recent_submissions = sorted(
        submissions,
        key=lambda item: (
            item.submitted_at is not None,
            item.submitted_at.timestamp() if item.submitted_at else 0,
        ),
        reverse=True,
    )[:6]
    reels = sorted(
        (item for item in active if item.output_recommendation in {"Reel", "Shorts"}),
        key=lambda item: (item.engagement_score, item.discussion_score),
        reverse=True,
    )[:6]
    patreon = [item for item in active if item.output_recommendation == "Patreon Discussion"][:6]
    industry = [item for item in active if "Industry Trend" in item.badges][:6]
    high_interest = sum(item.discussion_score >= 60 for item in all_items)
    fan_wars = sum("Fan War" in item.badges for item in all_items)
    generated = datetime.now().astimezone().strftime("%d %B %Y &middot; %H:%M %Z")
    markdown_path = markdown_path or path.with_name("briefing.md")
    markdown_href = escape(os.path.relpath(markdown_path, path.parent), quote=True)
    safe_public_url = escape(public_url.strip(), quote=True)
    canonical = f'<link rel="canonical" href="{safe_public_url}"><meta property="og:url" content="{safe_public_url}">' if safe_public_url else ""
    footer_export = "Static share edition: upload this one HTML file as-is." if self_contained else f'<a href="{markdown_href}">Open Markdown export</a>.'
    sections = "".join([
        _section("tonight", "If We Recorded Tonight", "THE EDITOR'S FIVE", tonight, ranked=True, empty="No story earns the microphone tonight.", self_contained=self_contained, fetch_images=fetch_images),
        _section("trending", "Trending Stories", "WHAT IS MOVING", trending, ranked=True, empty="No stories are trending yet.", self_contained=self_contained, fetch_images=fetch_images),
        _section("fan-war", "Fan War Watch", "THE TEMPERATURE CHECK", fan_war, ranked=True, empty="The fandoms are unusually peaceful today.", self_contained=self_contained, fetch_images=fetch_images),
        _section("listener-submissions", "Listener Submissions", "FROM THE AUDIENCE", recent_submissions, empty="No listener submissions collected.", self_contained=self_contained, fetch_images=fetch_images),
        _section("reels", "Best Reel Opportunities", "CUT FOR VERTICAL", reels, empty="No visual story is strong enough for a reel yet.", self_contained=self_contained, fetch_images=fetch_images),
        _section("patreon", "Best Patreon Discussions", "FOR THE MEMBERS", patreon, empty="No story currently rewards a deeper Patreon conversation.", self_contained=self_contained, fetch_images=fetch_images),
        _section("industry", "Industry Trend Watch", "BEYOND THE HEADLINES", industry, empty="No clear industry pattern has emerged yet.", self_contained=self_contained, fetch_images=fetch_images),
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
    .shell {{ width:min(100% - 24px,1280px); margin:auto; position:relative; }}
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
    .hero {{ padding:38px 0 3px; display:grid; gap:26px; }}
    .hero-label {{ margin:0; color:var(--pink); font-size:.7rem; font-weight:900; letter-spacing:.18em; text-transform:uppercase; }}
    h1 {{ margin:.5rem 0 .8rem; max-width:790px; font-family:Georgia,"Times New Roman",serif; font-size:clamp(2.55rem,12vw,5.8rem); font-weight:700; line-height:.92; letter-spacing:-.06em; }}
    h1 em {{ color:var(--yellow); font-style:normal; }}
    .hero-copy {{ margin:0; color:#d0cdc6; max-width:680px; font-family:Georgia,"Times New Roman",serif; font-size:1.03rem; }}
    .stats {{ display:grid; grid-template-columns:repeat(2,1fr); gap:10px; }}
    .stat {{ min-height:82px; padding:14px; border-top:3px solid var(--yellow); background:var(--panel); }}
    .stat:nth-child(even) {{ border-top-color:var(--pink); }} .stat b {{ display:block; font-size:1.8rem; line-height:1; }} .stat span {{ display:block; margin-top:8px; color:var(--muted); font-size:.61rem; font-weight:850; letter-spacing:.09em; text-transform:uppercase; }}
    .quick-nav {{ position:sticky; top:0; z-index:20; padding:10px 0; background:rgba(9,9,10,.94); backdrop-filter:blur(16px); border-bottom:1px solid var(--line); }}
    .quick-nav .shell {{ display:flex; gap:8px; overflow:auto; }}
    .quick-nav a {{ white-space:nowrap; padding:7px 10px; color:var(--muted); border-left:2px solid var(--line); font-size:.65rem; font-weight:900; text-transform:uppercase; letter-spacing:.08em; }}
    .quick-nav a:hover {{ color:var(--ink); border-color:var(--yellow); background:var(--yellow); }}
    main {{ padding-bottom:60px; }}
    .dashboard-section {{ padding:48px 0 4px; scroll-margin-top:58px; }}
    .section-heading {{ display:flex; justify-content:space-between; align-items:end; margin-bottom:18px; padding-bottom:12px; border-bottom:3px solid var(--text); }}
    .section-heading p {{ margin:0 0 5px; color:var(--pink); font-size:.72rem; font-weight:900; letter-spacing:.15em; }}
    h2 {{ margin:0; font-family:Georgia,"Times New Roman",serif; font-size:clamp(1.75rem,8vw,3.1rem); line-height:1; letter-spacing:-.045em; }}
    .section-heading>span {{ color:var(--yellow); font-size:1rem; font-weight:950; }}
    .card-grid {{ display:grid; grid-template-columns:1fr; gap:14px; }}
    .story-card {{ display:flex; flex-direction:column; gap:15px; min-width:0; padding:16px; overflow:hidden; background:linear-gradient(150deg,var(--panel),#101011); border:1px solid var(--line); border-radius:3px; box-shadow:0 15px 45px rgba(0,0,0,.2); }}
    .story-card:hover {{ border-color:#58585f; transform:translateY(-2px); transition:.18s ease; }}
    .media-wrap {{ position:relative; margin:-16px -16px 0; }}
    .story-media {{ position:relative; height:190px; overflow:hidden; background:radial-gradient(circle at 22% 30%,rgba(255,61,141,.5),transparent 32%),radial-gradient(circle at 78% 70%,rgba(255,230,0,.36),transparent 32%),#242428; }}
    .story-media img {{ width:100%; height:100%; display:block; object-fit:cover; }}
    .image-fallback {{ display:none; position:absolute; inset:0; place-items:center; color:rgba(255,255,255,.13); font-size:clamp(2rem,5vw,4.7rem); font-weight:950; letter-spacing:-.07em; transform:rotate(-7deg); }}
    .story-media.image-error .image-fallback {{ display:grid; }}
    .story-status {{ position:absolute; inset:14px 14px auto; display:flex; justify-content:space-between; align-items:center; gap:10px; pointer-events:none; }}
    .trend,.age {{ padding:6px 9px; border-radius:999px; background:rgba(12,12,13,.82); box-shadow:0 5px 20px rgba(0,0,0,.28); backdrop-filter:blur(9px); font-size:.62rem; font-weight:950; letter-spacing:.07em; text-transform:uppercase; }}
    .trend-up {{ color:var(--green); }} .trend-down {{ color:var(--pink); }} .trend-new {{ color:var(--yellow); }} .age {{ color:#ddd9d0; }}
    .card-top {{ display:flex; align-items:flex-start; justify-content:space-between; gap:10px; min-height:28px; }}
    .rank {{ display:grid; place-items:center; min-width:32px; height:32px; background:var(--yellow); color:var(--ink); font-family:Georgia,"Times New Roman",serif; font-size:1.05rem; font-weight:950; }}
    .badge-row {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .badge {{ padding:4px 7px; border:1px solid var(--line); color:var(--muted); font-size:.58rem; font-weight:950; letter-spacing:.07em; }}
    .badge-high-interest,.badge-breaking {{ color:var(--ink); background:var(--yellow); border-color:var(--yellow); }}
    .badge-fan-war,.badge-patreon {{ color:white; background:var(--pink); border-color:var(--pink); }}
    .badge-reel-idea,.badge-podcast {{ color:var(--green); border-color:rgba(113,230,160,.5); }}
    .eyebrow {{ margin:0 0 5px; color:var(--muted); font-size:.68rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }}
    .eyebrow span {{ color:var(--pink); }} h3 {{ margin:0; font-family:Georgia,"Times New Roman",serif; font-size:clamp(1.28rem,6vw,1.72rem); line-height:1.08; letter-spacing:-.025em; }}
    .story-dek {{ margin:10px 0 0; color:#c4c0b8; font-size:.86rem; line-height:1.5; }}
    .editorial-meta {{ display:grid; grid-template-columns:repeat(3,1fr); gap:1px; background:var(--line); border:1px solid var(--line); }} .editorial-meta>div {{ padding:9px; background:var(--panel-2); }} .editorial-meta b {{ display:block; color:var(--yellow); font-size:1rem; line-height:1; }} .editorial-meta span {{ display:block; margin-top:5px; color:var(--muted); font-size:.51rem; font-weight:900; letter-spacing:.06em; text-transform:uppercase; }} .editorial-meta>strong {{ grid-column:1/-1; padding:7px 9px; background:var(--ink); color:var(--pink); font-size:.58rem; letter-spacing:.1em; text-transform:uppercase; }}
    blockquote {{ margin:0; padding:13px 14px; color:#e9e5dd; background:var(--panel-2); border-left:3px solid var(--pink); font-family:Georgia,"Times New Roman",serif; font-size:.9rem; }} blockquote span {{ display:block; margin-bottom:5px; color:var(--pink); font-family:Inter,ui-sans-serif,system-ui,sans-serif; font-size:.56rem; font-weight:950; letter-spacing:.13em; }}
    .listener-signal {{ margin:0; color:var(--muted); font-size:.72rem; }}
    .card-actions {{ display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; padding-top:2px; }}
    .source-link,.copy-actions button {{ display:inline-flex; align-items:center; justify-content:center; min-height:34px; padding:8px 10px; border:1px solid var(--line); background:transparent; color:var(--text); font:inherit; font-size:.61rem; font-weight:850; letter-spacing:.03em; cursor:pointer; }}
    .source-link {{ border-color:rgba(255,230,0,.55); color:var(--yellow); }} .source-link.disabled {{ color:var(--muted); border-color:var(--line); cursor:default; }}
    .copy-actions {{ display:flex; flex-wrap:wrap; gap:6px; }} .copy-actions button:hover,.copy-actions button.copied {{ color:var(--ink); border-color:var(--yellow); background:var(--yellow); }}
    .copy-payload {{ position:fixed; left:-10000px; top:-10000px; width:1px; height:1px; opacity:0; pointer-events:none; }}
    details {{ margin-top:auto; border-top:1px solid var(--line); padding-top:14px; }} summary {{ cursor:pointer; color:var(--muted); font-size:.72rem; font-weight:850; text-transform:uppercase; letter-spacing:.06em; }} summary:hover {{ color:var(--yellow); }}
    .details-body {{ padding-top:8px; color:var(--muted); font-size:.84rem; }} .details-body p {{ margin:12px 0 0; }} .details-body strong {{ display:block; color:var(--text); font-size:.67rem; text-transform:uppercase; letter-spacing:.06em; }}
    .empty-state {{ grid-column:1/-1; padding:36px; color:var(--muted); border:1px dashed var(--line); text-align:center; }}
    footer {{ padding:38px 0 55px; color:var(--muted); border-top:1px solid var(--line); font-size:.8rem; }} footer a {{ color:var(--yellow); font-weight:850; }}
    .footer-grid {{ display:grid; grid-template-columns:minmax(0,1.6fr) minmax(240px,.6fr); gap:30px; align-items:end; }} .footer-about strong {{ display:block; margin-bottom:7px; color:var(--pink); font-size:.66rem; letter-spacing:.12em; }} .footer-about p {{ margin:0; max-width:820px; color:#d4d0c8; font-size:.9rem; }} .footer-meta {{ display:flex; flex-direction:column; align-items:flex-end; gap:8px; text-align:right; }} .producer-link {{ font-size:.72rem; }}
    @media (max-width:559px) {{ h1,h3 {{ overflow-wrap:anywhere; }} .card-actions,.copy-actions {{ align-items:stretch; flex-direction:column; width:100%; }} .source-link,.copy-actions button {{ width:100%; }} .footer-grid {{ grid-template-columns:1fr; }} .footer-meta {{ align-items:flex-start; text-align:left; }} }}
    @media (min-width:700px) {{ .shell {{ width:min(100% - 48px,1280px); }} header {{ padding-top:30px; }} .brand-line {{ align-items:center; flex-direction:row; justify-content:space-between; }} .brand-actions {{ width:auto; }} .share-button,.download-button {{ flex:none; }} .share-status {{ text-align:right; }} .hero {{ grid-template-columns:minmax(0,1.5fr) minmax(300px,.65fr); align-items:end; padding-top:52px; }} .card-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .story-media {{ height:220px; }} }}
    @media (min-width:1040px) {{ .card-grid {{ grid-template-columns:repeat(3,minmax(0,1fr)); }} #tonight .card-grid {{ grid-template-columns:repeat(6,minmax(0,1fr)); }} #tonight .story-card:nth-child(-n+2) {{ grid-column:span 3; }} #tonight .story-card:nth-child(n+3) {{ grid-column:span 2; }} #tonight .story-card:nth-child(-n+2) .story-media {{ height:280px; }} .dashboard-section {{ padding-top:66px; }} }}
    @media print {{ .quick-nav,details {{ display:none; }} body {{ background:white; color:black; }} .story-card,.stat {{ break-inside:avoid; box-shadow:none; }} }}
  </style>
</head>
<body data-public-url="{safe_public_url}">
  <header><div class="shell">
    <div class="brand-line"><div class="brand-lockup"><span class="brand-dot"></span><div class="wordmark" aria-label="KHANDAAN BOLLYWOOD RADAR"><span class="wordmark-khandaan">KHANDAAN</span><span class="wordmark-radar">BOLLYWOOD <em>RADAR</em></span></div></div><div><div class="brand-actions"><button class="share-button" type="button" id="share-dashboard">Share dashboard</button><button class="download-button" type="button" id="download-dashboard">Download HTML</button></div><p class="share-status" id="share-status" aria-live="polite"></p></div></div>
    <div class="date">{generated}</div>
    <div class="hero"><div><p class="hero-label">THE WEEK IN BOLLYWOOD</p><h1>What Bollywood fans are talking about <em>this week</em></h1><p class="hero-copy">Stories, debates and industry shifts selected for the Khandaan conversation.</p></div>
    <div class="stats"><div class="stat"><b>{len(all_items)}</b><span>Stories watched</span></div><div class="stat"><b>{high_interest}</b><span>Hot topics</span></div><div class="stat"><b>{len(reels)}</b><span>Reel picks</span></div><div class="stat"><b>{fan_wars}</b><span>Fan wars</span></div></div></div>
  </div></header>
  <nav class="quick-nav" aria-label="This week's desks"><div class="shell"><a href="#tonight">Tonight</a><a href="#trending">Trending</a><a href="#fan-war">Fan War</a><a href="#listener-submissions">Listeners</a><a href="#reels">Reels</a><a href="#patreon">Patreon</a><a href="#industry">Industry</a></div></nav>
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
