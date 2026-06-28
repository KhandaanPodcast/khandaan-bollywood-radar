# Local Smoke Test

This guide runs Khandaan Bollywood Radar on your own machine and produces the primary `dashboard.html` plus the `briefing.md` export in the project directory.

## 1. Open the project and create a virtual environment

Python 3.10 or newer is recommended.

```bash
cd /path/to/build-a-python-based-mvp-called
python3 -m venv .venv
source .venv/bin/activate
python --version
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## 2. Install dependencies

With the virtual environment active:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Optional quick check:

```bash
python -m unittest discover -s tests -v
```

All bundled tests should report `ok`.

## 3. Create `.env`

Copy the example file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` and add Reddit credentials only if you plan to enable Reddit. Editorial briefing fields are generated locally from metadata and do not require an LLM key.

## 4. Get Reddit API credentials

Reddit is optional, but it is needed to populate the Reddit section.

1. Sign in to the Reddit account that will own the application.
2. Visit <https://www.reddit.com/prefs/apps>.
3. Select **create another app** or **create app**.
4. Enter a name such as `Khandaan Bollywood Radar`.
5. Select the **script** application type.
6. Enter a description and an about URL if Reddit requests them.
7. Use `http://localhost:8080` as the redirect URI. This MVP uses client credentials, so it does not open that URI.
8. Create the app.
9. Copy the short ID displayed beneath the app name. This is the client ID.
10. Copy the value labelled `secret`.

Add them to `.env`:

```dotenv
REDDIT_CLIENT_ID=your_short_client_id
REDDIT_CLIENT_SECRET=your_reddit_secret
REDDIT_USER_AGENT=khandaan-bollywood-radar/0.1 (contact: you@example.com)
```

Use a real contact address in the user agent. Keep the secret private. Reddit may require app review or approval, and use of Reddit data remains subject to its current [Developer Terms](https://redditinc.com/policies/developer-terms) and [Data API Terms](https://redditinc.com/policies/data-api-terms).

To smoke-test without Reddit credentials, temporarily set `reddit.enabled: false` in `sources.yaml`.

## 5. Add news and Reddit sources

Edit `sources.yaml`. A small test configuration is:

```yaml
google_news:
  enabled: true
  language: en-IN
  country: IN
  keywords:
    - Bollywood
    - Hindi cinema
    - Shah Rukh Khan
  max_items_per_keyword: 5

reddit:
  enabled: true
  subreddits:
    - bollywood
    - BollyBlindsNGossip
  sort: hot
  limit_per_subreddit: 10
```

Valid Reddit sort values include `hot`, `new`, and `top`. Keep the first test small to reduce API traffic and make the output easy to inspect.

The rest of `sources.yaml` should retain these sections:

```yaml
x_inputs:
  file: x_inputs.md

listener_submissions:
  source: listener_submissions.csv

briefing:
  top_stories: 8
  reddit_items: 6
  listener_items: 8
```

Paths are resolved relative to the directory containing `sources.yaml`.

## 6. Add manual X inputs

The app does not scrape X. Add one public link or observation per line in `x_inputs.md`:

```markdown
# X / Twitter inputs

- https://x.com/example/status/123456789
- Fans are debating whether the new trailer reveals too much of the plot.
- Strong early response to the soundtrack, especially the dance number.
```

Markdown bullets are optional. Blank lines and headings beginning with `#` are ignored.

## 7. Add listener submissions

For the simplest test, edit `listener_submissions.csv`. Keep the header exactly as shown:

```csv
story_link,summary,source_platform,why_it_matters,submitter_name,credit_permission,patreon_member
https://example.com/story-one,New trailer has divided fans,YouTube,Could drive a useful conversation about marketing,Asha,yes,no
https://example.com/story-one?utm_source=newsletter,Another vote for the trailer discussion,X,Multiple listeners are asking about it,Dev,no,yes
https://example.com/story-two,A star addressed casting rumours,Instagram,Good short visual explainer opportunity,Meera,yes,no
```

The first two rows intentionally point to the same story. The briefing should group them, show two submissions, mark the grouped item as a Patreon-member submission, and only publicly credit names that have permission.

Boolean fields accept `yes/no`, `true/false`, `1/0`, or `y/n`.

You may add an optional `image_url` column with a direct HTTPS image or poster URL. It is not required; cards without an image use the built-in Khandaan artwork.

To use a public Google Sheet instead, give the sheet the same seven column names, make it readable by link, and set:

```yaml
listener_submissions:
  source: https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit?gid=0
```

A direct HTTPS CSV export URL also works. Private Google Sheets are not supported by this MVP.

## 8. Run the briefing generator

The sample local command that fetches configured sources and generates both outputs is:

```bash
python -m khandaan_radar --sources sources.yaml --output briefing.md
```

A successful run prints absolute paths similar to:

```text
Dashboard: /path/to/build-a-python-based-mvp-called/dashboard.html
Share file: /path/to/build-a-python-based-mvp-called/share_dashboard.html
Public-ready page: /path/to/build-a-python-based-mvp-called/public/index.html
Public URL: set DASHBOARD_PUBLIC_URL after uploading
Markdown export: /path/to/build-a-python-based-mvp-called/briefing.md
```

Double-click `dashboard.html` to open it. No server command is required. Use `briefing.md` when you need a portable text export.

Open `share_dashboard.html` with Wi-Fi disabled to confirm that the layout, text, controls, and branded image fallbacks remain available. Images fetched successfully during an online run are embedded directly; images that cannot be embedded fall back cleanly instead of creating a broken dependency.

Useful diagnostic runs:

```bash
# Fetch live news and Reddit
python -m khandaan_radar

# Test only local X and listener input processing
python -m khandaan_radar --offline
```

## 9. Check successful output

Open `dashboard.html` first. It should have a dark Khandaan-branded layout with yellow and pink accents, story cards, circular priority indicators, score bars, and these sections near the top:

1. `If We Recorded Tonight`
2. `Best Reel Opportunities`
3. `Best Patreon Discussions`
4. `Stories To Ignore`

Cards can display `HIGH INTEREST`, `FAN WAR`, `PATREON`, `BREAKING`, `REEL IDEA`, and `PODCAST` badges when the underlying story qualifies. Each card's planning notes can be expanded without leaving the page.

Cards also show story age, `UP`/`DOWN`/`NEW` trend estimates, discussion and fan-war scores out of 10, confidence status, and a direct source link. Use the three copy buttons to place podcast notes, a reel idea, or a Patreon post draft on the clipboard. Local files use a built-in fallback when the browser does not grant the modern Clipboard API.

The `briefing.md` export should contain all of these headings:

1. `Executive Summary`
2. `Khandaan Take`
3. `Top 3 Stories to Discuss`
4. `Best Patreon Discussion`
5. `Best Reel and Shorts Ideas`
6. `Main Episode Candidates`
7. `Fan War Watch`
8. `Industry Trend Watch`
9. `Listener Submissions`
10. `Ignore`
11. `If We Recorded Tonight`

For a fully configured live run, expect linked news items, Reddit discussions, manual X notes, and grouped listener stories arranged by editorial purpose rather than source. Every ranked story should show 0–100 scores plus its lifecycle, reason Khandaan should care, two or three discussion questions, related dashboard stories, Google News/Reddit/listener counts, and a confidence explanation. Listener notes preserve duplicate, Patreon-member, and permitted-credit signals. The final recording shortlist should contain at most five items, ordered primarily by discussion score.

All of these decisions come from deterministic metadata, watchlist, theme, recency, and source-relationship heuristics. The compatibility flag `--no-ai` is accepted but unnecessary.

Warnings for one network source do not stop other sources from producing the file. Read any warning carefully if a section is empty.

## Common errors

### `No module named ...`

The virtual environment is not active or dependencies were not installed. Activate `.venv` and run:

```bash
python -m pip install -r requirements.txt
```

### `Source config not found`

Run the command from the project directory, or pass the correct path with `--sources`.

### `Reddit is enabled but REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are not set`

Add both values to `.env`, restart the command, or set `reddit.enabled: false` in `sources.yaml`.

### Reddit `401`, `403`, or `429`

- `401`: recheck the client ID and secret; the client ID is the short value beneath the app name, not the app name.
- `403`: confirm the app is permitted to use Reddit's API and complies with Reddit's current developer requirements.
- `429`: wait before retrying and reduce `limit_per_subreddit` or the number of subreddits.

Also make sure `REDDIT_USER_AGENT` is descriptive and contains a real contact address.

### Google News is skipped or returns no items

Check your internet connection, use broader keywords, and verify `google_news.enabled: true`. A temporary Google News failure appears as a warning and does not prevent local inputs from being rendered.

### `Listener submissions are missing columns`

Restore all seven required CSV or Sheet headers exactly:

```text
story_link, summary, source_platform, why_it_matters, submitter_name, credit_permission, patreon_member
```

Remove leading or trailing spaces from the actual header cells.

### Google Sheet error or empty listener section

Confirm the URL is a Google Sheets URL, the correct tab's `gid` is present, and the sheet is readable without signing in. For private data, export it as CSV and use the local file instead.

### X section is empty

Confirm `x_inputs.file` points to the right file. Inputs must be on their own lines and must not begin with `#`.

### The briefing exists but some sections say `No items collected`

This is valid output when that source returned no records. Review terminal warnings, source enablement, input file paths, subreddit names, and search keywords. Use `--offline --no-ai` first to isolate local-file issues from API issues.
