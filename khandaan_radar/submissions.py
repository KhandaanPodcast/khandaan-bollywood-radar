from __future__ import annotations

import csv
import io
import os
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

HEADER_ALIASES = {
    "briefly explain what happened": "summary",
    "source platform": "source_platform",
    "why is this interesting controversial or worth discussing": "why_it_matters",
    "your name or handle": "submitter_name",
    "can we credit you": "credit_permission",
    "patreon member": "patreon_member",
    "image url": "image_url",
}


def _as_bool(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "y"} or normalized.startswith(("yes ", "yes,", "true "))


def _canonical_header(header: str) -> str:
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", header.strip().lower()).split())
    canonical = normalized.replace(" ", "_")
    if canonical in REQUIRED_COLUMNS or canonical == "image_url":
        return canonical
    if normalized.startswith("story link"):
        return "story_link"
    return HEADER_ALIASES.get(normalized, "")


def resolve_submission_source(configured_source: str) -> str:
    return os.getenv("LISTENER_SUBMISSIONS_URL", "").strip() or configured_source


def _google_sheet_csv_url(url: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        return url
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if parsed.path.rstrip("/").endswith("/export") and query.get("format") == ["csv"]:
        return url
    export_url = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv"
    return f"{export_url}&gid={query['gid'][0]}" if query.get("gid") else export_url


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


def load_submissions(source: str, base_dir: Path, *, warnings: list[str] | None = None) -> list[Submission]:
    warnings = warnings if warnings is not None else []
    text = _read_source(source, base_dir)
    if not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text))
    columns = {
        canonical: header
        for header in (reader.fieldnames or [])
        if (canonical := _canonical_header(header))
    }
    missing = REQUIRED_COLUMNS - set(columns)
    if missing:
        warnings.append(f"Listener submissions are missing required columns: {', '.join(sorted(missing))}")
        return []

    submissions = []
    for row_number, row in enumerate(reader, start=2):
        values = {
            column: (row.get(header) or "").strip()
            for column, header in columns.items()
        }
        if not any(values.get(column, "") for column in REQUIRED_COLUMNS):
            continue
        missing_values = sorted(column for column in REQUIRED_COLUMNS if not values.get(column, ""))
        if missing_values:
            warnings.append(
                f"Listener submission row {row_number} skipped; missing required fields: "
                f"{', '.join(missing_values)}"
            )
            continue
        submissions.append(
            Submission(
                story_link=values["story_link"],
                summary=values["summary"],
                source_platform=values["source_platform"],
                why_it_matters=values["why_it_matters"],
                submitter_name=values["submitter_name"],
                credit_permission=_as_bool(values["credit_permission"]),
                patreon_member=_as_bool(values["patreon_member"]),
                image_url=values.get("image_url", ""),
            )
        )
    return submissions


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
