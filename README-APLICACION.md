# Lex Go Trámite — actualización de marca y política OAuth

## Instalación sin afectar producción

1. Trabajar en `website-repair-test` y **no en `main`**.
2. Subir a la raíz del repositorio todos los archivos de este paquete salvo `README-APLICACION.md` (opcional).
3. Asegurarse de que no se crea una carpeta envolvente: `index.html`, `privacidad.html`, `politica-de-privacidad.html`, `seo-intelligence.html` y las imágenes deben quedar en la raíz.
4. Verificar la vista previa en Cloudflare: cabecera, navegación móvil, iconos, políticas y enlaces.
5. Revisar la política de privacidad con la persona responsable antes de desplegar. Confirmar que los informes son privados, se almacenan como artefactos 30 días, se protegen los secretos OAuth y que no se comparten datos fuera de lo descrito. El uso de Google/GitHub puede requerir información adicional sobre transferencias internacionales y encargados.
6. Crear pull request y revisar antes de fusionar a `main`.
7. **Solo después del despliegue de producción**, configurar en Google Auth Platform: logo `lexgotramite-oauth-logo-120.png`; URL principal `https://lexgotramite.com/seo-intelligence`; política `https://lexgotramite.com/politica-de-privacidad`; dominio autorizado `lexgotramite.com`. Verificar ambas URL públicamente.
8. Solicitar de nuevo la verificación de marca cuando Google pueda leer las páginas y la información sea exacta. La verificación depende de Google; no está garantizada.

## Archivos principales

- `index.html`: imagen principal del sitio, footer de privacidad.
- `privacidad.html`: política general existente y enlace OAuth.
- `politica-de-privacidad.html`: disclosures específicos para SEO Intelligence.
- `seo-intelligence.html`: página pública que describe la app OAuth.
- `lexgotramite-brand-logo.png`: marca horizontal utilizada por el sitio.
- `favicon.ico`, `favicon-16x16.png`, `favicon-32x32.png`, `apple-touch-icon.png`, `logo.png`: imagen de marca para iconos ya usados por las páginas sin modificar sus URLs.
- `og-image.png`: imagen social de marca para enlaces existentes.
- `lexgotramite-oauth-logo-120.png`: logo para subir a Google Cloud (no necesita estar publicado).
- `lexgotramite-oauth-logo-512.png`: logo maestro.

Este paquete **no** contiene credenciales, ni modifica workflows, artículos, sitemap, estado de publicación o configuración de Cloudflare.
