# Share Dashboard

Each generator run creates three HTML variants:

- `dashboard.html` is the normal local dashboard.
- `share_dashboard.html` is a single self-contained file intended for file sharing.
- `public/index.html` is the public-hosting-ready version.
- `index.html` is the same public page at the repository root for GitHub Pages.

Listener submissions are included in all three HTML files and in `briefing.md`. These are
static snapshots: new Google Form responses appear only after the generator is run again.
Set `LISTENER_SUBMISSIONS_URL` to the public Google Sheet CSV export before generating, or
leave it blank to use the local CSV configured in `sources.yaml`.

If a response is missing a required field, the generator prints a warning and leaves that
row out of every shared output. Review those warnings before publishing.

## Use the Share button

The **Share dashboard** button behaves differently depending on configuration:

- With `DASHBOARD_PUBLIC_URL` configured, it opens the phone or computer's native share sheet. Browsers without a share sheet copy the public link instead.
- Without a public URL, it downloads a fresh `khandaan-dashboard.html` file that can be attached or uploaded.

The adjacent **Download HTML** button always downloads the currently displayed dashboard as one HTML file.

## Dropbox or Google Drive

Upload `share_dashboard.html` as a normal file, then use the service's Share control. Recipients may need to download the file and open it in their browser because Dropbox and Google Drive are file-sharing services, not general static website hosts.

The share export contains its CSS, scripts, and successfully fetched images inside the HTML. Source article links still point to their original websites by design.

## GitHub Pages

GitHub Pages is the simplest option for a normal public web URL.

1. Create or choose a GitHub repository.
2. Use the generated root `index.html` when GitHub Pages serves the repository root. Keep `public/index.html` for other hosts or portable deployment.
3. In the repository settings, open **Pages** and select that branch and folder as the publishing source.
4. Wait for GitHub to show the published URL, commonly `https://USERNAME.github.io/REPOSITORY/`.
5. Add that URL to `.env`:

```dotenv
DASHBOARD_PUBLIC_URL=https://USERNAME.github.io/REPOSITORY/
```

6. Run the generator again and re-upload `public/index.html`.

The regenerated page includes the URL as its canonical address, and its Share button shares that public URL.

You can also pass the URL for one run:

```bash
python -m khandaan_radar --public-url https://USERNAME.github.io/REPOSITORY/
```

## Other static hosts

Any service that accepts a static `index.html` can use `public/index.html`. Set `DASHBOARD_PUBLIC_URL` to the final HTTPS address and regenerate once so the Share button and page metadata use the correct link.

No upload happens automatically. This avoids storing Dropbox, Google, or GitHub credentials in the local MVP and prevents accidentally publishing listener information.

Before sharing publicly, review the Listener Submissions section. Submitter names are shown
only when `credit_permission` is affirmative, but story links, summaries, and audience notes
are still published in the generated page.
