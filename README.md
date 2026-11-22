# Lex Go Trámite — Website repository

Static Spanish-language legal-services website deployed at **https://lexgotramite.com/**. The uploaded ZIP does not include an unambiguous hosting configuration, so **verify hosting rewrites and redirects in your provider before deployment**. Search-indexed live pages demonstrate extensionless routes exist, but this does not prove all historical URLs resolve.

## Directory map

| Location | Purpose | Deployment guidance |
| --- | --- | --- |
| `index.html` | Homepage | Preserve root location and layout |
| `*.html` (root) | Existing public pages and legacy paths | Preserve until each route/canonical is reviewed |
| `blog/*.html` | Published articles and blog listing | Public URLs; do not move |
| `drafts/*.json` | Source drafts for the publisher | Never publish by moving files manually |
| `*.json` (root) | Legacy/source content | Preserve; audit consumers before relocating |
| `scripts/publish_next_article.py` | **Active** publication script | Invoked by both workflows |
| `scripts/google_search_console_notify.py` | Optional Search Console notification | Requires GitHub secrets |
| `scripts/check_links.py` | Internal link, asset and sitemap validator | Read-only except audit JSON report |
| `publish_state.json` | Publication state and order | Do not regenerate or reset |
| `.github/workflows/publish-daily-seo.yml` | **Only scheduled** daily publisher, 08:15 UTC | Also supports manual runs |
| `.github/workflows/publish.yml` | Manual publishing compatibility workflow | No schedule; shares concurrency lock |
| `sitemap.xml`, `robots.txt` | Search engine discovery | Preserve public location |
| `docs/` and public PNG/ICO assets | Downloadable and web assets | Preserve URLs |

## Check site links

Run `python scripts/check_links.py` from anywhere inside the repository (Python 3.10+). The report is generated at `reports/link-audit.json`. To validate link fragments too, run `python scripts/check_links.py --strict-fragments`.

The validator resolves ordinary `.html` paths and equivalent extensionless HTML routes **as local site conventions**; it does not independently establish that your deployment actually supports them. It validates locally referenced assets and sitemap targets, and reports canonical route mismatches for human review. It does not guarantee live external URL availability or the execution paths of JavaScript-generated navigation.

## Automated publication

The main schedule belongs to `.github/workflows/publish-daily-seo.yml`, at `15 8 * * *` (08:15 UTC). Both workflows support manual execution and use the same GitHub Actions concurrency group with `cancel-in-progress: false`. Both run the link validator before and after publication. The publishing script itself reads `drafts/`, updates `blog/`, `blog/index.html`, `index.html`, `sitemap.xml`, and `publish_state.json`. The optional Search Console integration uses GitHub Actions secrets; do not save tokens in the repository.

**Before merging:** review [AUDIT_REPORT.md](AUDIT_REPORT.md), validate a test deployment, and confirm published canonical URLs and root-level duplicate pages. Do not force-push or deploy changes without checking the resulting preview.
