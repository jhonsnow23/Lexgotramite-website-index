from pathlib import Path
import json
import html
import re
from datetime import date, datetime
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DRAFTS_DIR = ROOT / "drafts"
BLOG_DIR = ROOT / "blog"
STATE_FILE = ROOT / "publish_state.json"
SITEMAP_FILE = ROOT / "sitemap.xml"
BLOG_INDEX_FILE = BLOG_DIR / "index.html"
HOME_FILE = ROOT / "index.html"

BLOG_DIR.mkdir(exist_ok=True)

SPANISH_MONTHS = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
    7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
}


def format_date_es(iso_date: str) -> str:
    try:
        dt = datetime.strptime(iso_date, "%Y-%m-%d").date()
        return f"{dt.day} {SPANISH_MONTHS[dt.month]} {dt.year}"
    except Exception:
        return iso_date


def parse_display_date_to_iso(text: str):
    if not text:
        return None
    text = html.unescape(text).strip()
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    return None


def sitemap_lastmods():
    if not SITEMAP_FILE.exists():
        return {}
    try:
        root = ET.fromstring(SITEMAP_FILE.read_text(encoding="utf-8"))
    except ET.ParseError:
        return {}
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    lastmods = {}
    for url in root.findall("sm:url", ns):
        loc = url.findtext("sm:loc", default="", namespaces=ns).strip()
        lastmod = url.findtext("sm:lastmod", default="", namespaces=ns).strip()
        if not loc or not lastmod:
            continue
        slug = Path(loc).stem
        if slug and slug != "index":
            lastmods[slug] = lastmod
    return lastmods


def normalize_state(raw_state):
    if not isinstance(raw_state, dict):
        raw_state = {}

    published_dates = raw_state.get("published_dates", {})
    if not isinstance(published_dates, dict):
        published_dates = {}

    raw_published = raw_state.get("published", [])
    published_order = []

    if isinstance(raw_published, list):
        for item in raw_published:
            if isinstance(item, str):
                published_order.append(item)
            elif isinstance(item, dict):
                slug = item.get("slug")
                if slug:
                    published_order.append(slug)
                    if item.get("published_at"):
                        published_dates.setdefault(slug, item["published_at"])

    deduped_order = []
    seen = set()
    for slug in published_order:
        if slug not in seen:
            deduped_order.append(slug)
            seen.add(slug)

    state = {
        "published": deduped_order,
        "published_dates": published_dates,
        "last_published": raw_state.get("last_published"),
    }

    sitemap_dates = sitemap_lastmods()
    for slug in deduped_order:
        if slug not in state["published_dates"] and slug in sitemap_dates:
            state["published_dates"][slug] = sitemap_dates[slug]

    return state


def load_state():
    if STATE_FILE.exists():
        return normalize_state(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    return normalize_state({"published": []})


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def render_article(draft, published_at: str):
    sections_html = []
    for section in draft["sections"]:
        if section["type"] == "paragraph":
            sections_html.append(f"""
<section>
  <h2 class="text-2xl font-bold text-slate-900">{html.escape(section['title'])}</h2>
  <p class="mt-3 text-slate-700">{html.escape(section['content'])}</p>
</section>
""")
        elif section["type"] == "list":
            items = "\n".join(f"<li>{html.escape(item)}</li>" for item in section["items"])
            sections_html.append(f"""
<section>
  <h2 class="text-2xl font-bold text-slate-900">{html.escape(section['title'])}</h2>
  <ul class="mt-3 list-disc pl-6 space-y-2 text-slate-700">
    {items}
  </ul>
</section>
""")
    display_date = format_date_es(published_at)
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
  <meta property="article:published_time" content="{published_at}" />
  <meta property="og:image" content="https://lexgotramite.com/og-image.png" />
  <meta name="twitter:image" content="https://lexgotramite.com/og-image.png" />
  <link rel="icon" href="/favicon.ico" sizes="any" />
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />
  <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png" />
  <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
  <link rel="manifest" href="/site.webmanifest" />
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-white text-slate-800 font-sans antialiased">
  <main class="max-w-4xl mx-auto px-4 py-12 sm:py-16">
    <a href="/index.html" class="text-indigo-700 hover:underline">← Volver a la página principal</a>
    <p class="mt-6 text-sm text-slate-500">{html.escape(draft.get('category','Extranjería'))} • {html.escape(display_date)}</p>
    <h1 class="mt-2 text-4xl md:text-5xl font-bold text-slate-900">{html.escape(draft['title'])}</h1>
    <p class="mt-5 text-lg text-slate-600">{html.escape(draft['intro'])}</p>
    <div class="mt-10 space-y-10">
      {''.join(sections_html)}
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


def extract_title_desc_date(article_path: Path):
    content = article_path.read_text(encoding="utf-8")
    title_match = re.search(r"<title>(.*?)\s*\|\s*Lex Go Trámite</title>", content, re.S)
    desc_match = re.search(r'<meta name="description" content="(.*?)"', content, re.S)
    date_match = re.search(r'<meta property="article:published_time" content="(.*?)"', content, re.S)
    if not date_match:
        date_match = re.search(r'<p class="mt-6 text-sm text-slate-500">.*?•\s*(.*?)</p>', content, re.S)
    title = html.unescape(title_match.group(1).strip()) if title_match else article_path.stem.replace("-", " ").title()
    desc = html.unescape(desc_match.group(1).strip()) if desc_match else f"Guía práctica sobre {article_path.stem.replace('-', ' ')}."
    raw_date = html.unescape(date_match.group(1).strip()) if date_match else ""
    iso_date = parse_display_date_to_iso(raw_date) or raw_date
    display_date = format_date_es(iso_date) if iso_date else ""
    return title, desc, display_date, iso_date


def update_sitemap(url, published_at):
    if not SITEMAP_FILE.exists():
        SITEMAP_FILE.write_text('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>', encoding="utf-8")
    content = SITEMAP_FILE.read_text(encoding="utf-8")
    entry_pattern = re.compile(rf"<url>\s*<loc>{re.escape(url)}</loc>[\s\S]*?</url>", re.S)
    entry = f"""
  <url>
    <loc>{url}</loc>
    <lastmod>{published_at}</lastmod>
    <priority>0.8</priority>
  </url>
"""
    if url in content:
        content = entry_pattern.sub(entry.strip(), content)
    else:
        content = content.replace("</urlset>", entry + "\n</urlset>")
    SITEMAP_FILE.write_text(content, encoding="utf-8")


def list_blog_articles():
    return [p for p in BLOG_DIR.glob("*.html") if p.name != "index.html"]


def list_blog_articles_for_display(state=None):
    articles = list_blog_articles()
    if state is None:
        state = load_state()
    published_order = state.get("published", [])
    order_map = {slug: idx for idx, slug in enumerate(published_order)}

    def sort_key(path: Path):
        slug = path.stem
        iso_date = state.get("published_dates", {}).get(slug, "")
        if slug in order_map:
            return (1, iso_date or "0000-00-00", order_map[slug])
        try:
            return (0, datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d"), 0)
        except FileNotFoundError:
            return (0, "0000-00-00", 0)

    return sorted(articles, key=sort_key, reverse=True)


def update_blog_index():
    state = load_state()
    articles = list_blog_articles_for_display(state)
    total_articles = len(articles)
    cards = []
    for article_file in articles:
        title, desc, display_date, _ = extract_title_desc_date(article_file)
        date_line = f'<p class="mt-2 text-sm text-slate-500">{html.escape(display_date)}</p>' if display_date else ""
        cards.append(f"""
        <article class="bg-white border border-slate-200 rounded-2xl p-6 shadow-soft hover:-translate-y-0.5 transition">
          <h2 class="text-xl font-semibold text-slate-900">
            <a href="/blog/{article_file.name}" class="hover:text-indigo-700">{html.escape(title)}</a>
          </h2>
          {date_line}
          <p class="mt-3 text-slate-600">{html.escape(desc)}</p>
        </article>
""")
    page = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Blog de extranjería | Lex Go Trámite</title>
  <meta name="description" content="Guías prácticas sobre papeles en España, residencia, arraigo social, NIE y homologaciones." />
  <meta name="theme-color" content="#1e1b4b" />
  <meta property="og:image" content="https://lexgotramite.com/og-image.png" />
  <meta name="twitter:image" content="https://lexgotramite.com/og-image.png" />
  <link rel="icon" href="/favicon.ico" sizes="any" />
  <link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />
  <link rel="icon" type="image/png" sizes="16x16" href="/favicon-16x16.png" />
  <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
  <link rel="manifest" href="/site.webmanifest" />
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          colors: {{ brand: {{ 600:'#4f46e5',700:'#4338ca',800:'#3730a3',900:'#1e1b4b' }} }},
          boxShadow: {{ soft:'0 10px 30px rgba(15,23,42,.12)' }}
        }}
      }}
    }}
  </script>
</head>
<body class="bg-slate-50 text-slate-800 font-sans antialiased">
  <main class="max-w-6xl mx-auto px-4 py-10 sm:py-14">
    <a href="/index.html" class="inline-flex items-center text-indigo-700 hover:underline">← Volver a la página principal</a>
    <section class="mt-6 rounded-3xl bg-gradient-to-br from-slate-900 via-brand-800 to-brand-600 text-white shadow-soft overflow-hidden">
      <div class="px-6 py-10 sm:px-10 sm:py-12">
        <p class="text-sm font-semibold uppercase tracking-[0.2em] text-white/70">Lex Go Trámite</p>
        <h1 class="mt-3 text-4xl sm:text-5xl font-bold">Blog de extranjería</h1>
        <p class="mt-4 max-w-3xl text-white/80 text-base sm:text-lg">Contenido pensado para extranjeros que quieren vivir, trabajar o estudiar legalmente en España. Aquí tienes todos los artículos publicados, ordenados de más reciente a más antiguo.</p>
        <div class="mt-6 inline-flex items-center rounded-full bg-white/10 px-4 py-2 text-sm font-medium text-white/90 ring-1 ring-white/20">{total_articles} artículos publicados</div>
      </div>
    </section>
    <div class="mt-10 grid gap-6 md:grid-cols-2">
      {''.join(cards)}
    </div>
  </main>
  <script src="/cookies.js"></script>
</body>
</html>
"""
    BLOG_INDEX_FILE.write_text(page, encoding="utf-8")


def update_home_blog_section():
    if not HOME_FILE.exists():
        return
    home = HOME_FILE.read_text(encoding="utf-8")
    state = load_state()
    all_articles = list_blog_articles_for_display(state)
    latest = all_articles[:8]
    total_articles = len(all_articles)
    cards = []
    for article_file in latest:
        title, desc, display_date, _ = extract_title_desc_date(article_file)
        meta_line = f"Extranjería • {display_date}" if display_date else "Extranjería"
        cards.append(f"""
        <article class="bg-white border border-slate-200 rounded-3xl shadow-soft overflow-hidden">
          <div class="p-6 sm:p-8">
            <p class="text-sm text-slate-500">{html.escape(meta_line)}</p>
            <h3 class="mt-2 text-2xl font-serif font-bold text-slate-900">
              <a href="/blog/{article_file.name}" class="hover:text-brand-700">
                {html.escape(title)}
              </a>
            </h3>
            <p class="mt-4 text-slate-600 text-base sm:text-lg">
              {html.escape(desc)}
            </p>
            <div class="mt-6">
              <a href="/blog/{article_file.name}"
                 class="inline-flex items-center justify-center rounded-xl bg-brand-700 px-5 py-3 text-white font-semibold hover:bg-brand-800 transition">
                Leer artículo
              </a>
            </div>
          </div>
        </article>
""")
    replacement = f"""<!-- Blog -->
  <section id="blog" class="py-16 sm:py-20 bg-slate-50">
    <div class="container px-4">
      <div class="text-center max-w-3xl mx-auto">
        <h2 class="text-3xl md:text-4xl font-serif font-bold text-slate-900">Blog</h2>
        <p class="mt-3 text-slate-600 text-base sm:text-lg">
          Guías claras sobre regularización, papeles y trámites de extranjería en España.
        </p>
      </div>

      <div class="mt-10 grid gap-6 md:grid-cols-2">
        {''.join(cards)}
      </div>

      <div class="mt-10 flex justify-center">
        <a href="/blog/" class="inline-flex items-center justify-center gap-2 rounded-2xl bg-slate-900 px-6 py-3 text-white font-semibold shadow-soft hover:bg-brand-700 transition">
          Ver todos los {total_articles} artículos
          <span aria-hidden="true">→</span>
        </a>
      </div>
    </div>
  </section>"""
    home = re.sub(r'<!-- Blog -->[\s\S]*?<!-- Cita \(Zoho Bookings\) -->', replacement + "\n\n  <!-- Cita (Zoho Bookings) -->", home, count=1)
    HOME_FILE.write_text(home, encoding="utf-8")


def republish_existing_articles_with_real_dates():
    state = load_state()
    changed = False
    for article_file in list_blog_articles():
        slug = article_file.stem
        draft_file = DRAFTS_DIR / f"{slug}.json"
        if not draft_file.exists():
            continue
        published_at = state.get("published_dates", {}).get(slug)
        if not published_at:
            _, _, _, extracted_iso = extract_title_desc_date(article_file)
            published_at = extracted_iso or date.today().isoformat()
            state.setdefault("published_dates", {})[slug] = published_at
            changed = True
        draft = json.loads(draft_file.read_text(encoding="utf-8"))
        article_file.write_text(render_article(draft, published_at), encoding="utf-8")
    if changed:
        save_state(state)


def publish_next():
    state = load_state()
    published = set(state.get("published", []))
    queue = state.get("draft_queue", []) if isinstance(state.get("draft_queue"), list) else []

    next_draft = None
    if queue:
        while queue:
            candidate_slug = queue[0]
            candidate_file = DRAFTS_DIR / f"{candidate_slug}.json"
            if candidate_slug in published:
                queue.pop(0)
                continue
            if candidate_file.exists():
                next_draft = candidate_file
                break
            queue.pop(0)
        state["draft_queue"] = queue

    if next_draft is None:
        drafts = sorted(DRAFTS_DIR.glob("*.json"))
        for draft_file in drafts:
            if draft_file.stem not in published:
                next_draft = draft_file
                break

    if next_draft is None:
        print("No hay más artículos pendientes.")
        state["last_published"] = None
        save_state(state)
        return

    draft = json.loads(next_draft.read_text(encoding="utf-8"))
    published_at = date.today().isoformat()
    slug = draft["slug"]
    (BLOG_DIR / f"{slug}.html").write_text(render_article(draft, published_at), encoding="utf-8")
    update_sitemap(f"https://lexgotramite.com/blog/{slug}.html", published_at)
    state.setdefault("published_dates", {})[slug] = published_at
    state["published"] = [item for item in state.get("published", []) if item != slug] + [slug]
    if state.get("draft_queue") and state["draft_queue"] and state["draft_queue"][0] == slug:
        state["draft_queue"].pop(0)
    state["last_published"] = {
        "slug": slug,
        "url": f"https://lexgotramite.com/blog/{slug}.html",
        "published_at": published_at,
        "title": draft.get("title", slug),
    }
    save_state(state)
    print(f"Publicado: {slug}")


def main():
    publish_next()
    republish_existing_articles_with_real_dates()
    update_blog_index()
    update_home_blog_section()


if __name__ == "__main__":
    main()
