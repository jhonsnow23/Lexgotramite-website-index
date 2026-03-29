from pathlib import Path
import json
import html
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
DRAFTS_DIR = ROOT / "drafts"
BLOG_DIR = ROOT / "blog"
STATE_FILE = ROOT / "publish_state.json"
SITEMAP_FILE = ROOT / "sitemap.xml"
BLOG_INDEX_FILE = BLOG_DIR / "index.html"

BLOG_DIR.mkdir(exist_ok=True)

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"published": []}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def render_article(draft):
    parts = []
    for section in draft["sections"]:
        if section["type"] == "paragraph":
            parts.append(f"""
<section>
  <h2 class="text-2xl font-bold text-slate-900">{html.escape(section['title'])}</h2>
  <p class="mt-3 text-slate-700">{html.escape(section['content'])}</p>
</section>
""")
        else:
            items = "\n".join(f"<li>{html.escape(item)}</li>" for item in section["items"])
            parts.append(f"""
<section>
  <h2 class="text-2xl font-bold text-slate-900">{html.escape(section['title'])}</h2>
  <ul class="mt-3 list-disc pl-6 space-y-2 text-slate-700">
    {items}
  </ul>
</section>
""")
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(draft['title'])} | Lex Go Trámite</title>
  <meta name="description" content="{html.escape(draft['description'])}" />
  <link rel="canonical" href="https://lexgotramite.com/blog/{html.escape(draft['slug'])}.html" />
  <meta property="og:title" content="{html.escape(draft['title'])}" />
  <meta property="og:description" content="{html.escape(draft['description'])}" />
  <meta property="og:type" content="article" />
  <meta property="og:url" content="https://lexgotramite.com/blog/{html.escape(draft['slug'])}.html" />
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-white text-slate-800 font-sans antialiased">
  <main class="max-w-4xl mx-auto px-4 py-12 sm:py-16">
    <a href="/index.html" class="text-indigo-700 hover:underline">← Volver a la página principal</a>
    <p class="mt-6 text-sm text-slate-500">{html.escape(draft.get('category','Extranjería'))} • {html.escape(draft.get('date', str(date.today())))}</p>
    <h1 class="mt-2 text-4xl md:text-5xl font-bold text-slate-900">{html.escape(draft['title'])}</h1>
    <p class="mt-5 text-lg text-slate-600">{html.escape(draft['intro'])}</p>
    <div class="mt-10 space-y-10">
      {''.join(parts)}
    </div>
    <div class="mt-12 rounded-2xl bg-slate-50 border border-slate-200 p-6">
      <h2 class="text-2xl font-bold text-slate-900">¿Necesitas ayuda con tu caso?</h2>
      <p class="mt-3 text-slate-600">Te ayudamos a conseguir tus papeles en España, revisar tu documentación y elegir el mejor siguiente paso.</p>
      <div class="mt-5">
        <a href="/index.html#cita" class="inline-flex items-center justify-center rounded-xl bg-indigo-700 px-5 py-3 text-white font-semibold hover:bg-indigo-800 transition">
          Reservar una cita
        </a>
      </div>
    </div>
  </main>
  <script src="/cookies.js"></script>
</body>
</html>
"""

def update_sitemap(url):
    if not SITEMAP_FILE.exists():
        SITEMAP_FILE.write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>', encoding="utf-8")
    content = SITEMAP_FILE.read_text(encoding="utf-8")
    if url in content:
        return
    entry = f"""
  <url>
    <loc>{url}</loc>
    <lastmod>{date.today().isoformat()}</lastmod>
    <priority>0.8</priority>
  </url>
"""
    content = content.replace("</urlset>", entry + "\n</urlset>")
    SITEMAP_FILE.write_text(content, encoding="utf-8")

def update_blog_index():
    cards = []
    for article_file in sorted(BLOG_DIR.glob("*.html")):
        if article_file.name == "index.html":
            continue
        name = article_file.stem.replace("-", " ")
        title = name.title()
        cards.append(f'''
        <article class="bg-white border border-slate-200 rounded-2xl p-6 shadow-soft">
          <h2 class="text-xl font-semibold text-slate-900">
            <a href="/blog/{article_file.name}" class="hover:text-indigo-700">{html.escape(title)}</a>
          </h2>
          <p class="mt-3 text-slate-600">Guía práctica sobre {html.escape(name)}.</p>
        </article>
''')
    page = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Blog de extranjería | Lex Go Trámite</title>
  <meta name="description" content="Guías prácticas sobre papeles en España, residencia, arraigo social, NIE y homologaciones." />
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-white text-slate-800 font-sans antialiased">
  <main class="max-w-6xl mx-auto px-4 py-12 sm:py-16">
    <a href="/index.html" class="text-indigo-700 hover:underline">← Volver a la página principal</a>
    <h1 class="mt-6 text-4xl font-bold text-slate-900">Blog de extranjería</h1>
    <p class="mt-4 text-slate-600">Contenido pensado para extranjeros que quieren vivir, trabajar o estudiar legalmente en España.</p>
    <div class="mt-10 grid gap-6 md:grid-cols-2">
      {''.join(cards)}
    </div>
  </main>
  <script src="/cookies.js"></script>
</body>
</html>
"""
    BLOG_INDEX_FILE.write_text(page, encoding="utf-8")

def main():
    state = load_state()
    published = set(state.get("published", []))
    drafts = sorted(DRAFTS_DIR.glob("*.json"))
    next_draft = None
    for draft_file in drafts:
        if draft_file.stem not in published:
            next_draft = draft_file
            break
    if next_draft is None:
        print("No hay más artículos pendientes.")
        return
    draft = json.loads(next_draft.read_text(encoding="utf-8"))
    (BLOG_DIR / f"{draft['slug']}.html").write_text(render_article(draft), encoding="utf-8")
    update_sitemap(f"https://lexgotramite.com/blog/{draft['slug']}.html")
    update_blog_index()
    published.add(next_draft.stem)
    state["published"] = sorted(published)
    save_state(state)
    print(f"Publicado: {draft['slug']}")

if __name__ == "__main__":
    main()
