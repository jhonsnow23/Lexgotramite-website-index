# Automatización de publicación SEO con GitHub

## Qué hace
Publica automáticamente 1 artículo al día desde `drafts/` hacia `blog/` usando GitHub Actions.

## Qué debes subir
- `.github/workflows/publish-daily-seo.yml`
- `scripts/publish_next_article.py`
- `drafts/`
- `publish_state.json`

## Cómo activarlo
1. Sube todo al repositorio.
2. En GitHub ve a **Settings → Actions → General**.
3. Activa **Read and write permissions**.
4. Ve a **Actions** y ejecuta `Publicar artículo SEO diario` manualmente la primera vez.

## Qué actualiza
- `/blog/*.html`
- `/blog/index.html`
- `sitemap.xml`
