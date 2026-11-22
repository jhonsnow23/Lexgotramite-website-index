# Lex Go Trámite — Safe maintenance audit

Audit baseline: uploaded ZIP `Lexgotramite-website-index-main.zip`, 22 November 2026. Changes were made to an extracted copy, not the live GitHub repository.

## Findings

- **178 HTML pages** examined locally; **1 proven unresolved internal link in the original ZIP** (in root-level `informe-de-arraigo-social.html`, pointing to `/blog/razones-humanitarias-proteccion-internacional-2026`, which does not exist in the ZIP). The corresponding blog card was removed from that anomalous root-level index copy; no new legal article was fabricated.
- **0 unresolved internal links** in the updated ZIP under the repository's `.html`/extensionless routing conventions. `sitemap.xml` has 178 entries, all resolving locally.
- **71 root-level HTML pages report a canonical route different from their own filename route**. Some are visibly copies/misplaced generated blog pages. This is potentially significant for SEO but was **not mass-corrected**, because their public purpose, existing indexing, and any live redirects must be verified individually. `informe-de-arraigo-social.html` itself contains a full blog index with a `/blog/` canonical, not the corresponding article. This is a separate review priority.
- **Two scheduled publishing workflows** previously ran at 08:00 and 08:15 UTC. Both invoke `scripts/publish_next_article.py`. This could publish twice daily when drafts were available. The second workflow is now manual-only, with both using a shared non-cancelling concurrency group. The original daily workflow remains scheduled at 08:15 UTC.
- The root-level `publish_next_article.py` is **CPython bytecode, despite its `.py` extension**, not the active source. It is retained to avoid deleting unknown legacy material; `scripts/publish_next_article.py` is the source used by the workflows. Recommended removal only after history/consumer verification.
- Many files share identical bytes, including legacy root HTML/JSON counterparts. No mass deduplication or moves occurred, because they might be public paths or inputs to other processes.
- The ZIP does not contain an explicit hosting rewrite configuration. Live search results indicate extensionless URLs are indexed, but this does **not** establish parity between test and production routing.

## Actual file changes

| File | Change |
| --- | --- |
| `informe-de-arraigo-social.html` | Removed one card pointing to a nonexistent article |
| `.github/workflows/publish.yml` | Removed the second daily schedule; kept manual trigger and publication actions; added shared concurrency and pre/post link checks |
| `.github/workflows/publish-daily-seo.yml` | Kept existing 08:15 UTC schedule; added concurrency and pre/post link checks |
| `scripts/check_links.py` | Added local link, asset, fragment (optional), sitemap, canonical-warning and dependency-map audit |
| `.gitignore` | Added exclusions for Python caches, local reports, virtual environments and local env files |
| `README.md` | Replaced brief notes with directory map, workflow description, commands and risks |
| `AUDIT_REPORT.md` | Added this audit and change log |

No site pages were renamed, published article bodies were edited, public URL slugs changed, drafts removed, publication state reset, or production services modified.

## Validation completed

- Local HTML link + asset scan: **1 before → 0 after**.
- Local sitemap resolution: **178/178 targets found**.
- Fragment scan (`--strict-fragments`): **0 missing fragments** detected in parsed HTML attributes.
- Python syntax compilation: **passed** for all three scripts.
- GitHub Actions YAML parse: **passed** for both workflows.
- Publisher executed **in a disposable copy**: completed with `No hay más artículos pendientes.`; resulting local link scan still returned **0** missing targets. All original `drafts/` and `publish_state.json` in the deliverable were left unchanged.
- No browser-driven visual/mobile/cookie QA, no GitHub Actions remote execution, and no real hosting-level HTTP 404/301 crawl were possible inside this local archive audit. These remain required before claiming production verification.

## SEO, automation and hosting checks still required before merging

1. Review the 71 canonical/filename mismatches in `reports/link-audit.json` with a live crawler and search-engine index data; some may be intentional legacy aliases, others erroneous copies. Do not blanket-change their canonicals.
2. Confirm the precise hosting platform, `.html` clean-URL handling, HTTP status and redirect behavior (including www, trailing slash and `.html` variants) on a staging deployment.
3. Verify no links are generated dynamically by JavaScript to missing paths, and test mobile menus, contact flows and cookie consent in a real browser.
4. Confirm repository branch protection and workflow permissions; review historical runs for duplicate publications.
5. The legacy root-level bytecode file and identical content groups are intentionally left in place until Git history and references can verify their safe removal.

**No live GitHub branch or pull request was created**: this working copy came from a ZIP with no authenticated repository write connection. Preserve the original ZIP as the rollback artifact, import the updated ZIP into a dedicated branch, and verify before merge.
