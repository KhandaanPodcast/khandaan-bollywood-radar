# Khandaan Bollywood Radar

_What Bollywood fans are actually talking about._

A simple, local-first Python MVP that collects Bollywood news, Reddit discussion, manual X/Twitter notes, and listener submissions into a visual `dashboard.html`. A Markdown version remains available as `briefing.md` for export. OpenAI can enrich editorial angles, hooks, and Khandaan Takes.

For a complete local smoke test, see [TESTING.md](TESTING.md).

## What it does

- Reads all source choices from `sources.yaml`.
- Fetches Google News RSS searches for configured Bollywood keywords.
- Fetches Reddit posts through Reddit's official OAuth API.
- Reads manually pasted X links or observations from `x_inputs.md` (it does not scrape X).
- Deduplicates stories using canonical URLs and similar titles.
- Scores every story and listener submission for discussion value, priority, controversy, engagement, and confidence; then adds badges, an output recommendation, a conversational Khandaan Take, an editorial angle, a hook, and a patron poll.
- Reads listener submissions from a local CSV, an HTTPS CSV export, or a public Google Sheet URL.
- Groups duplicate submissions, highlights high-interest and Patreon-member items, and recommends Patreon, podcast, or reel treatment.
- Builds a branded, self-contained visual dashboard and a Markdown export on every run.

## Setup

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add `OPENAI_API_KEY` to `.env`. To enable Reddit, create a Reddit **script** application and add its client ID and secret too. Change the placeholder contact in `REDDIT_USER_AGENT` to a real address.

## Configure sources

Edit `sources.yaml`. Google News keywords and Reddit subreddits are ordinary YAML lists. Relative file paths are resolved from the directory containing `sources.yaml`.

For listener submissions, set `listener_submissions.source` to one of:

```yaml
listener_submissions:
  source: listener_submissions.csv
```

```yaml
listener_submissions:
  source: https://docs.google.com/spreadsheets/d/SHEET_ID/edit?gid=0
```

The Google Sheet must be shared so the export URL is readable. A direct HTTPS CSV export also works. Required columns are:

`story_link, summary, source_platform, why_it_matters, submitter_name, credit_permission, patreon_member`

Use `yes/no`, `true/false`, or `1/0` for the two boolean fields. Names appear in the briefing only when `credit_permission` is affirmative.

Listener CSVs and Sheets may optionally add an `image_url` column containing a direct HTTPS poster or story-image URL. Google News and Reddit images are detected automatically when their feeds expose one.

## Run

Paste X links or text into `x_inputs.md`, then run:

```bash
python -m khandaan_radar
```

When the command finishes, double-click `dashboard.html`. It opens directly in Chrome, Safari, Firefox, or Edge and does not need a local server. The page contains its styling, scripts, and successfully fetched story images inside one HTML file; unavailable images use a branded fallback.

Every run also creates:

- `share_dashboard.html`: one portable, self-contained file for Dropbox, Google Drive, email, or chat.
- `public/index.html`: the static public-site version for GitHub Pages or another static host.

See [SHARING.md](SHARING.md) for upload and public-link instructions.

Useful modes:

```bash
# Exercise the complete local pipeline without network or OpenAI
python -m khandaan_radar --offline --no-ai

# Use another config or output location
python -m khandaan_radar --sources my_sources.yaml --dashboard my_dashboard.html --output my_briefing.md
```

The primary output is `dashboard.html`; `briefing.md` is generated alongside it. Individual network failures are reported as warnings so other available sources can still produce a dashboard. Without an OpenAI key, explicitly pass `--no-ai`; this keeps accidental silent degradation out of normal editorial runs.

## Tests

```bash
python -m unittest discover -s tests
```

The rule-based editorial planner works with `--offline --no-ai`, including scoring and format recommendations. The MVP intentionally avoids a database, scheduler, X API dependency, and private Google credentials. It is designed to run by hand or from a local cron job and to keep its inputs inspectable.
