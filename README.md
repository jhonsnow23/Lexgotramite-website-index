# Automatización de publicación SEO con GitHub

## Qué hace
Publica automáticamente **1 artículo al día** desde `drafts/` hacia `blog/` usando GitHub Actions.

## Archivos
- `.github/workflows/publish-daily-seo.yml`
- `scripts/publish_next_article.py`
- `drafts/*.json`
- `publish_state.json`

## Cómo usarlo
Sube estas carpetas y archivos a la raíz de tu repositorio.
GitHub Actions publicará un artículo nuevo cada día y actualizará:
- `blog/`
- `blog/index.html`
- `sitemap.xml`

## Publicación manual
En GitHub → Actions → `Publicar artículo SEO diario` → `Run workflow`


## Extra
- La home (`index.html`) se actualiza automáticamente para mostrar los últimos artículos del blog.
- Este paquete ya incluye 4 artículos nuevos publicados para que el bloque Blog no se quede estático.
