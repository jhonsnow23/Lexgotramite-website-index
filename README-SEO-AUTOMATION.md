# Automatización de publicación SEO con GitHub

## Qué hace
Publica automáticamente 1 artículo al día desde `drafts/` hacia `blog/` usando GitHub Actions.

## Qué actualiza en cada ejecución
- `/blog/*.html`
- `/blog/index.html`
- `/index.html` (bloque del blog en portada)
- `sitemap.xml`
- `publish_state.json`
- `search_console_last_inspection.json` (solo si configuras Search Console)

## Cómo activarlo
1. Sube todo al repositorio.
2. En GitHub ve a **Settings → Actions → General**.
3. Activa **Read and write permissions**.
4. Ve a **Actions** y ejecuta `Publicar artículo SEO diario` manualmente la primera vez.

## Qué corrige esta versión
- La portada ya no ordena por nombre de archivo: muestra los artículos por **fecha real de publicación**.
- Cada tarjeta del blog en la home muestra la **fecha de publicación correcta**.
- Cada artículo guarda su fecha con `article:published_time` para que no se mezclen fechas falsas o repetidas.

## Automatización con Google Search Console
Esta automatización **no fuerza el indexado** de posts normales. Lo que sí hace es:
- enviar/actualizar el sitemap en Search Console,
- inspeccionar la última URL publicada,
- guardar la respuesta en `search_console_last_inspection.json`.

### Secrets que debes crear en GitHub
En **Settings → Secrets and variables → Actions**, añade:
- `GSC_CLIENT_ID`
- `GSC_CLIENT_SECRET`
- `GSC_REFRESH_TOKEN`
- `GSC_SITE_URL`
- `GSC_SITEMAP_URL`

### Valores esperados
- `GSC_SITE_URL`: la propiedad exacta de Search Console. Ejemplos:
  - `sc-domain:lexgotramite.com`
  - `https://lexgotramite.com/`
- `GSC_SITEMAP_URL`:
  - `https://lexgotramite.com/sitemap.xml`

## Advertencia importante
Si no configuras esos secrets, la publicación seguirá funcionando igual. Solo se saltará el paso de Search Console.
