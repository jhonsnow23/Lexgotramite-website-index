#!/usr/bin/env python3
"""Read-only Search Console intelligence; never publishes or edits site content.

Python standard library only. Requires the same OAuth secrets as the existing
Search Console notification script. Output files go to reports/ (gitignored).
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
TOPICS = {
    'post_regularization': ['regularizacion', 'renovar', 'renovacion', 'modificar', 'modificacion', 'autorizacion', 'residencia', 'tarjeta', 't ie', 'extranjeria'],
    'nationality': ['nacionalidad', 'nacionalizar', 'ccse', 'dele', 'jura', 'ciudadania', 'expediente nacionalidad'],
}
LEGAL_HINTS = ('regularizacion', 'nacionalidad', 'renovar', 'renovacion', 'residencia', 'autorizacion', 'arraigo', 'extranjeria')

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s).lower()) if not unicodedata.combining(c))

def slugify(s):
    return re.sub(r'-+', '-', re.sub('[^a-z0-9]+', '-', norm(s))).strip('-')[:90]

def topic_for(q):
    n = norm(q)
    if any(x in n for x in TOPICS['nationality']):
        return 'nationality'
    if any(x in n for x in TOPICS['post_regularization']):
        return 'post_regularization'
    return 'other'

def intent_for(q):
    n = norm(q)
    if any(x in n for x in ('precio', 'abogado', 'gestor', 'asesoria', 'tramitar')):
        return 'professional_assistance'
    if any(x in n for x in ('denegad', 'rechaz', 'recurso', 'caduc', 'perder', 'requerimiento')):
        return 'urgent_problem'
    if any(x in n for x in ('estado', 'expediente', 'consulta')):
        return 'application_status'
    if any(x in n for x in ('document', 'papeles', 'certificado')):
        return 'documents'
    if any(x in n for x in ('requisito', 'puedo', 'derecho', 'cuando puedo', 'cuantos anos')):
        return 'eligibility'
    if any(x in n for x in ('como', 'solicitar', 'pasos', 'plazo', 'renovar', 'modificar')):
        return 'procedure'
    return 'information'

def oauth_token():
    required = ('GSC_CLIENT_ID', 'GSC_CLIENT_SECRET', 'GSC_REFRESH_TOKEN')
    missing = [x for x in required if not os.getenv(x)]
    if missing:
        raise RuntimeError('Missing secrets: ' + ', '.join(missing))
    body = urllib.parse.urlencode({
        'client_id': os.environ['GSC_CLIENT_ID'],
        'client_secret': os.environ['GSC_CLIENT_SECRET'],
        'refresh_token': os.environ['GSC_REFRESH_TOKEN'],
        'grant_type': 'refresh_token',
    }).encode()
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=body, method='POST')
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.load(resp)['access_token']

def fetch_rows(token, site, start, end, dimensions=('query', 'page'), row_cap=10000):
    # Search Analytics can omit anonymous and low-volume queries. Values are not
    # total Google search volume. Avoid unbounded paging and retry loops.
    rows = []
    encoded = urllib.parse.quote(site, safe='')
    url = f'https://www.googleapis.com/webmasters/v3/sites/{encoded}/searchAnalytics/query'
    for offset in range(0, row_cap, 25000):
        payload = json.dumps({'startDate': start, 'endDate': end, 'dimensions': list(dimensions),
                              'rowLimit': min(25000, row_cap - offset), 'startRow': offset,
                              'type': 'web'}).encode()
        req = urllib.request.Request(url, data=payload, method='POST', headers={
            'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=50) as resp:
            batch = json.load(resp).get('rows', [])
        rows.extend(batch)
        if len(batch) < min(25000, row_cap - offset):
            break
    return rows

def known_slugs():
    published = {p.stem for p in ROOT.glob('*.html')}
    published.update(p.stem for p in (ROOT / 'blog').glob('*.html'))
    published.update(p.stem for p in (ROOT / 'drafts').glob('*.json'))
    return published

def analyze(rows, slugs=None):
    slugs = slugs if slugs is not None else known_slugs()
    by_query = {}
    for row in rows:
        keys = row.get('keys', [])
        if not keys or not isinstance(keys[0], str):
            continue
        q = keys[0].strip()
        if not q or topic_for(q) == 'other':
            continue
        e = by_query.setdefault(q, {'query': q, 'clicks': 0, 'impressions': 0,
                                    'position_weighted': 0.0, 'pages': set()})
        imp = max(0, int(row.get('impressions', 0)))
        e['clicks'] += max(0, int(row.get('clicks', 0)))
        e['impressions'] += imp
        e['position_weighted'] += max(0, float(row.get('position', 0))) * imp
        if len(keys) > 1:
            e['pages'].add(keys[1])
    out = []
    for q, item in by_query.items():
        imp = item['impressions']
        if not imp:
            continue
        pos = item['position_weighted'] / imp
        ctr = item['clicks'] / imp
        slug = slugify(q)
        exact_duplicate = slug in slugs
        topic = topic_for(q)
        intent = intent_for(q)
        # Transparent heuristic, not a search volume / conversion prediction.
        demand = min(100.0, imp / 5)
        topic_score = 100 if topic in ('nationality', 'post_regularization') else 0
        assistance = 90 if intent in ('professional_assistance', 'urgent_problem') else 60
        gap = 15 if exact_duplicate else (80 if 4 <= pos <= 20 else 60)
        timeliness = 50  # Needs independent official legal verification.
        score = round(.30 * demand + .25 * topic_score + .20 * assistance + .15 * gap + .10 * timeliness, 1)
        out.append({'query': q, 'topic': topic, 'intent': intent, 'clicks': item['clicks'],
                    'impressions': imp, 'ctr': round(ctr, 4), 'average_position': round(pos, 2),
                    'landing_pages': sorted(item['pages']), 'proposed_slug': slug,
                    'exact_slug_exists': exact_duplicate, 'priority_score': score,
                    'recommended_action': 'review_existing' if exact_duplicate else 'review_for_draft',
                    'legal_review_required': True,
                    'verification_status': 'NOT_VERIFIED',
                    'suggested_official_sources': ['https://www.boe.es/',
                        'https://www.inclusion.gob.es/', 'https://www.mjusticia.gob.es/']})
    return sorted(out, key=lambda x: (-x['priority_score'], -x['impressions'], x['query']))

def fetch_live():
    site = os.getenv('GSC_SITE_URL', '').strip()
    if not site:
        raise RuntimeError('GSC_SITE_URL is required (exact verified property, including sc-domain: when appropriate)')
    token = oauth_token()
    today = dt.date.today()
    # GSC reporting typically lags; use windows ending at least 3 days ago.
    end = today - dt.timedelta(days=3)
    windows = {}
    for n in (7, 28, 90):
        windows[str(n)] = fetch_rows(token, site, (end - dt.timedelta(days=n-1)).isoformat(), end.isoformat())
    return windows, {'source': 'google_search_console_api', 'site': site,
                     'data_end_date': end.isoformat(), 'retrieved_at': today.isoformat(),
                     'limitations': 'Property search impressions, not overall Google keyword volumes; query rows may be withheld or truncated.'}

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-json', type=Path, help='Offline fixture: JSON object with windows 7/28/90 or a rows list')
    p.add_argument('--out', type=Path, default=ROOT / 'reports' / 'seo_intelligence.json')
    args = p.parse_args(argv)
    if args.input_json:
        raw = json.loads(args.input_json.read_text(encoding='utf8'))
        windows = raw if isinstance(raw, dict) else {'28': raw}
        metadata = {'source': 'offline_fixture', 'verified_google_data': False}
    else:
        windows, metadata = fetch_live()
        metadata['verified_google_data'] = True
    reports = {str(n): analyze(rows) for n, rows in windows.items() if isinstance(rows, list)}
    result = {'metadata': metadata, 'windows': reports,
              'safety': 'READ ONLY; recommendations are not legally verified or authorized for publication.'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    md = args.out.with_suffix('.md')
    selected = reports.get('28') or next(iter(reports.values()), [])
    lines = ['# Lex Go Trámite — informe SEO', '', f"Fuente: **{metadata['source']}**", '',
             'Los datos de Search Console no equivalen al volumen total de búsquedas en Google.', '',
             '## Oportunidades (requieren validación legal y editorial)', '',
             '| Consulta | Impresiones | Clics | CTR | Posición | Prioridad | Acción |',
             '|---|---:|---:|---:|---:|---:|---|']
    for i in selected[:30]:
        q = i['query'].replace('|', '\\|')
        lines.append(f"| {q} | {i['impressions']} | {i['clicks']} | {i['ctr']:.1%} | {i['average_position']:.1f} | {i['priority_score']} | {i['recommended_action']} |")
    if not selected:
        lines.append('Sin consultas relevantes disponibles: no se proponen publicaciones.')
    md.write_text('\n'.join(lines) + '\n', encoding='utf8')
    print(f'Written {args.out} and {md} — {len(selected)} opportunities; no site content changed')
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f'SEO analysis unavailable: {exc}', file=sys.stderr)
        sys.exit(2)
