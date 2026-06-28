# Khandaan Bollywood Radar

_What Bollywood fans are actually talking about._

A simple, local-first Python MVP that collects Bollywood news, Reddit discussion, manual X/Twitter notes, and listener submissions into a visual `dashboard.html`. A Markdown version remains available as `briefing.md` for export. All editorial intelligence is generated deterministically from source metadata, watchlists, themes, and relationships between dashboard stories.

For a complete local smoke test, see [TESTING.md](TESTING.md).

## What it does

- Reads all source choices from `sources.yaml`.
- Fetches Google News RSS searches for configured Bollywood keywords.
- Fetches Reddit posts through Reddit's official OAuth API.
- Reads manually pasted X links or observations from `x_inputs.md` (it does not scrape X).
- Deduplicates stories using canonical URLs and similar titles.
- Scores every story and listener submission for discussion value, priority, controversy, engagement, and confidence; then adds badges and an output recommendation.
- Turns every ranked story into an editorial briefing with a lifecycle, a metadata-based reason to care, discussion questions, related dashboard stories, source counts, and a confidence explanation.
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

To enable Reddit, create a Reddit **script** application and add its client ID and secret to `.env`. Change the placeholder contact in `REDDIT_USER_AGENT` to a real address.

## Configure sources

Edit `sources.yaml`. Google News keywords and Reddit subreddits are ordinary YAML lists. Relative file paths are resolved from the directory containing `sources.yaml`.

The default listener source is the checked-in `listener_submissions.csv`. You can change
`listener_submissions.source` in `sources.yaml`:

```yaml
listener_submissions:
  source: listener_submissions.csv
```

```yaml
listener_submissions:
  source: https://docs.google.com/spreadsheets/d/SHEET_ID/edit?gid=0
```

For deployment or local overrides, set `LISTENER_SUBMISSIONS_URL` in `.env` instead:

```dotenv
LISTENER_SUBMISSIONS_URL=https://docs.google.com/spreadsheets/d/SHEET_ID/export?format=csv
```

When `LISTENER_SUBMISSIONS_URL` is non-empty, it takes precedence over
`listener_submissions.source`. Leave it blank to continue using the configured local CSV.
The Google Sheet must be shared so anyone with the link can read it. A normal Google Sheet
URL is converted to its CSV export automatically, and a direct HTTPS CSV export works too.

Required fields are:

`story_link, summary, source_platform, why_it_matters, submitter_name, credit_permission, patreon_member`

Local CSV files can use those names directly. Google Form response sheets can also use the
question headings from the provided form, including `Story Link: Example: ...`, `Briefly
explain what happened.`, `Source Platform`, `Why is this interesting, controversial or worth
discussing?`, `Your Name or Handle`, `Can We Credit You?`, and `Patreon Member`.

Use `yes/no`, `true/false`, or `1/0` for the two boolean fields. Names appear in the briefing only when `credit_permission` is affirmative.

Every non-empty response is validated. A row missing any required field is skipped and a
row-numbered warning is printed; a sheet or CSV missing required columns is skipped with a
warning listing those columns. Other valid submissions still appear in `dashboard.html`,
`briefing.md`, `share_dashboard.html`, `public/index.html`, and the root `index.html`.

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
- `index.html`: an identical root copy for GitHub Pages deployments that serve the repository root.

See [SHARING.md](SHARING.md) for upload and public-link instructions.

Useful modes:

```bash
# Exercise the complete local pipeline without network
python -m khandaan_radar --offline

# Use another config or output location
python -m khandaan_radar --sources my_sources.yaml --dashboard my_dashboard.html --output my_briefing.md
```

The primary output is `dashboard.html`; `briefing.md` is generated alongside it. Individual network failures are reported as warnings so other available sources can still produce a dashboard. The deprecated `--no-ai` flag remains accepted for compatibility but is no longer needed.

## Tests

```bash
python3 -m unittest discover -s tests
```

The metadata-based editorial planner works offline, including scoring, story intelligence, and format recommendations. The MVP intentionally avoids a database, scheduler, X API dependency, LLM dependency, and private Google credentials. It is designed to run by hand or from a local cron job and to keep its inputs inspectable.
