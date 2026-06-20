from __future__ import annotations

import json
import os

from .models import Story, Submission


SYSTEM_PROMPT = """You are the editorial producer for Khandaan, a sharp, funny, culturally informed Bollywood podcast. Be fair, specific, and concise. Do not invent facts. Return valid JSON only."""


def generate_editorial(stories: list[Story], reddit: list[Story], x_items: list[Story], submissions: list[Submission]) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    payload = {
        "stories": [
            {
                "title": x.title, "summary": x.summary[:500], "platform": x.platform,
                "priority_score": x.priority_score, "discussion_score": x.discussion_score,
                "controversy_score": x.controversy_score, "engagement_score": x.engagement_score,
                "confidence_score": x.confidence_score, "badges": x.badges,
                "topic_category": x.topic_category, "audience_temperature": x.audience_temperature,
                "output_recommendation": x.output_recommendation,
            }
            for x in [*stories, *reddit, *x_items]
        ],
        "listener_submissions": [
            {
                "summary": x.summary, "why": x.why_it_matters, "patreon": x.patreon_member,
                "duplicate_count": x.duplicate_count, "priority_score": x.priority_score,
                "discussion_score": x.discussion_score, "controversy_score": x.controversy_score,
                "engagement_score": x.engagement_score, "confidence_score": x.confidence_score,
                "badges": x.badges,
                "topic_category": x.topic_category, "audience_temperature": x.audience_temperature,
                "output_recommendation": x.output_recommendation,
            }
            for x in submissions
        ],
    }
    prompt = """Enrich the rule-based editorial planning data without changing scores, categories, temperatures, or best-use assignments. Return a JSON object with exactly two keys:
story_enrichments: an object mapping every story title exactly to an object containing editorial_angle, suggested_hook, suggested_patron_poll, and khandaan_take.
submission_enrichments: an object mapping every listener summary exactly to an object containing editorial_angle, suggested_hook, suggested_patron_poll, and khandaan_take.

Each angle must add a useful line of inquiry rather than recap the headline. Hooks should sound smart, funny, skeptical, and lightly conversational, never cruel or breathless. Polls must offer a real editorial choice. The khandaan_take must sound like a natural spoken reaction among informed friends on a Bollywood podcast: conversational, culturally aware, lightly funny, and skeptical without impersonating or attributing words to a named host. Avoid business jargon. Label rumours as unverified and distinguish evidence from inference. Do not repeat raw fields.\n\nINPUT:\n""" + json.dumps(payload, ensure_ascii=False)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        temperature=0.4,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
    )
    return json.loads(response.choices[0].message.content or "{}")


def fallback_editorial() -> dict:
    return {
        "story_enrichments": {},
        "submission_enrichments": {},
    }
