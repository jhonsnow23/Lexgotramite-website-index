# SEO intelligence upgrade — safe staged implementation

## What is implemented

- Read-only Search Console Search Analytics collection (7, 28 and 90-day windows, web search, query/page dimensions, max 10,000 rows per window).
- Transparent heuristic prioritization for post-regularization and nationality-by-residence search questions.
- Local existing-slug check, recommendations to review existing content before creating duplicates.
- JSON and Markdown opportunity reports, produced under ignored `reports/`.
- Daily report-only GitHub Actions workflow, with no write permissions, commit/push, content generation, or publishing.
- Offline fixtures and unit tests.

## What is deliberately NOT automated yet

No articles are drafted or published by this reporting workflow. Search Console rows do not establish what everyone searches for or what the current law says. No live API connection, legal source verification, Search Console indexing coverage pull, legal change monitoring, topic-level semantic deduplication, or editorial approval interface has been verified here. Keep those as future supervised phases rather than making unsupported automatic legal claims.

The pre-existing daily blog publisher is **unchanged** and continues selecting from its pre-approved drafts; the SEO report does not affect its publication queue.

## Configure existing credentials

In GitHub repository Settings → Secrets and variables → Actions, set the secrets already used by the existing Search Console notifier:

- `GSC_CLIENT_ID`
- `GSC_CLIENT_SECRET`
- `GSC_REFRESH_TOKEN`
- `GSC_SITE_URL` — exact property identifier from Search Console (e.g. `sc-domain:lexgotramite.com` or the URL-prefix property)

Use an authorized, read-only Search Console API identity where feasible. Never include secrets in screenshot, generated files, ZIP or Git commits. The account needs access to the Search Console property; API access must be enabled in the corresponding Google Cloud project.

## How to run

```sh
python -m unittest discover -s tests -v
python scripts/check_links.py
python scripts/seo_intelligence.py  # requires live credentials
python scripts/seo_intelligence.py --input-json tests/example_gsc_rows.json  # synthetic sample
```

Read `reports/seo_intelligence.md` or `reports/seo_intelligence.json`. The GitHub Actions run exposes the same report as a downloadable artifact under **SEO intelligence (read only)**. The workflow will schedule only after its YAML is present on the default branch. It does not run automatically just because a test branch is deployed to Cloudflare Pages.

## Before any publication based on this report

1. Verify applicable current regulations and transitional regimes with BOE and competent government guidance. Do not assume a regularization authorization follows an ordinary renewal route.
2. Check whether the intent is already addressed by an existing article; the slug match is a first-pass safety check only.
3. Approve precise claims, sources, authorship and proposed text before it enters the existing publisher's draft queue.
4. Validate all links, canonical URLs, sitemap and the preview deployment, and confirm no site content or publish state was modified by the SEO reporter.

## Deployment

Add files to the `website-repair-test` branch and review the diff. This add-on does not change existing HTML, the blog, drafts, production workflows, or `publish_state.json`. Do not merge it into `main` until tests and the preview are approved. A successful preview deployment alone does not prove Search Console API access.
