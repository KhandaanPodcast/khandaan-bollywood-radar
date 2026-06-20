from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .dedupe import canonical_url, normalized_title
from .models import Submission
from .scoring import rank_submissions


REQUIRED_COLUMNS = {
    "story_link", "summary", "source_platform", "why_it_matters", "submitter_name",
    "credit_permission", "patreon_member",
}


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _google_sheet_csv_url(url: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        return url
    gid = parse_qs(urlparse(url).query).get("gid", ["0"])[0]
    return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv&gid={gid}"


def _read_source(source: str, base_dir: Path) -> str:
    if source.startswith(("http://", "https://")):
        import requests

        response = requests.get(_google_sheet_csv_url(source), timeout=20)
        response.raise_for_status()
        return response.text
    path = Path(source)
    if not path.is_absolute():
        path = base_dir / path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig")


def load_submissions(source: str, base_dir: Path) -> list[Submission]:
    text = _read_source(source, base_dir)
    if not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"Listener submissions are missing columns: {', '.join(sorted(missing))}")
    return [
        Submission(
            story_link=(row.get("story_link") or "").strip(),
            summary=(row.get("summary") or "").strip(),
            source_platform=(row.get("source_platform") or "").strip(),
            why_it_matters=(row.get("why_it_matters") or "").strip(),
            submitter_name=(row.get("submitter_name") or "Anonymous").strip(),
            credit_permission=_as_bool(row.get("credit_permission") or ""),
            patreon_member=_as_bool(row.get("patreon_member") or ""),
            image_url=(row.get("image_url") or "").strip(),
        )
        for row in reader
        if any((row.get(column) or "").strip() for column in REQUIRED_COLUMNS)
    ]


def group_submissions(items: list[Submission]) -> list[Submission]:
    groups: dict[str, Submission] = {}
    for item in items:
        key = canonical_url(item.story_link) or normalized_title(item.summary)
        if key in groups:
            existing = groups[key]
            existing.duplicate_count += 1
            existing.patreon_member = existing.patreon_member or item.patreon_member
            if item.credit_permission:
                existing.submitters.append(item.submitter_name)
            if len(item.why_it_matters) > len(existing.why_it_matters):
                existing.why_it_matters = item.why_it_matters
        else:
            item.submitters = [item.submitter_name] if item.credit_permission else []
            groups[key] = item
    return rank_submissions(list(groups.values()))
