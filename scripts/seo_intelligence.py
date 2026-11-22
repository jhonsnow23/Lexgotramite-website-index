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

# V2 — review-only query clustering and editorial calendar.
# Stable intent groups deliberately prevent 'residencia' from becoming a giant
# catch-all cluster. A single query is assigned to one specific group.
STOPWORDS = set('de del la las el los en para por con sin una uno un y o a al que como cual cuanto cuantos se es su mi tu españa espana español española espanola'.split())
COMPETITOR_SIGNALS = (
    'lex sanz', 'parainmigrantes', 'balcells', 'rodenas abogados',
    'legalteam', 'tolentino', 'extranjeria24',
)
GROUPS = {
    'regularization_processing': ('Regularización: plazos y estado del expediente', 'post_regularization'),
    'post_regularization_renewal': ('Renovación tras regularización extraordinaria', 'post_regularization'),
    'residence_renewal': ('Renovación de residencia', 'post_regularization'),
    'long_term_residence': ('Residencia de larga duración y tarjeta', 'post_regularization'),
    'residency_options': ('Tipos y requisitos de residencia legal', 'post_regularization'),
    'nationality_requirements': ('Nacionalidad española por residencia: requisitos', 'nationality'),
    'nationality_documents': ('Nacionalidad por residencia: documentos', 'nationality'),
    'nationality_application': ('Nacionalidad por residencia: solicitud y estado', 'nationality'),
    'nationality_ceremony': ('Nacionalidad: jura y pasos posteriores', 'nationality'),
    'nationality_exams': ('Nacionalidad: exámenes CCSE y DELE', 'nationality'),
    'regularization_other': ('Regularización: otras preguntas', 'post_regularization'),
    'residency_other': ('Residencia: otras preguntas', 'post_regularization'),
}

def tokens(s):
    return set(re.findall(r'[a-z0-9]+', norm(s))) - STOPWORDS

def discard_reason(q):
    n = norm(q)
    if any(term in n for term in COMPETITOR_SIGNALS):
        return 'competitor_name'
    # Local professional searches have ambiguous geographic relevance. Do not
    # suppress information searches just because they mention a region.
    if re.search(r'\b(abogado|abogados|gestoria|asesoria)\b', n) and re.search(
        r'\b(?:(?:en|de)\s+)?(cantabria|elgoibar|bilbao|valencia|sevilla|barcelona|santiago de compostela)\b', n
    ):
        return 'local_service_unverified'
    return None

def cluster_for(q):
    n = norm(q)
    if re.search(r'\b(nacionalidad|nacionalizar|ciudadania|ccse|dele|jura)\b', n):
        if 'jura' in n: return 'nationality_ceremony'
        if re.search(r'\b(ccse|dele|examen|prueba)\b', n): return 'nationality_exams'
        if re.search(r'\b(document|papel|certificad|antecedent)', n): return 'nationality_documents'
        if re.search(r'\b(expediente|estado|tramite|solicitud|solicitar|resolucion|presentar)\b', n): return 'nationality_application'
        return 'nationality_requirements'
    regular = bool(re.search(r'regulariz|regularis', n))
    renew = bool(re.search(r'\brenov|renovar|renuev|prorroga|modificac', n))
    if regular and renew: return 'post_regularization_renewal'
    if regular and re.search(r'\b(tarda|tardando|tiempo|plazo|resolucion|expediente|estado|demora)\b', n):
        return 'regularization_processing'
    if regular: return 'regularization_other'
    if re.search(r'\b(larga duracion|permanente)\b', n):return 'long_term_residence'
    if renew and re.search(r'\b(residencia|permiso|tarjeta|nie|autorizacion)\b', n):return 'residence_renewal'
    if re.search(r'\b(residencia|residir|autorizacion)\b', n):
        if re.search(r'\b(tipo|tipos|legal|requisito|obtener|conseguir)\b', n):return 'residency_options'
        return 'residency_other'
    return None

def existing_index(root=ROOT):
    """Non-destructive inventory: published pages and drafts (no text rewrite)."""
    inv = []
    for folder in (root, root / 'blog'):
        if folder.exists():
            for f in sorted(folder.glob('*.html')):
                inv.append({'path':f.relative_to(root).as_posix(), 'slug':f.stem,
                            'draft':False,'tokens':tokens(f.stem)})
    folder=root/'drafts'
    if folder.exists():
        for f in sorted(folder.glob('*.json')):
            inv.append({'path':f.relative_to(root).as_posix(), 'slug':f.stem,
                        'draft':True,'tokens':tokens(f.stem)})
    return inv

def resolve_landing(url, root=ROOT):
    parsed=urllib.parse.urlsplit(url)
    if parsed.hostname not in ('lexgotramite.com','www.lexgotramite.com'):
        return None
    path=urllib.parse.unquote(parsed.path).lstrip('/')
    if not path: path='index'
    candidates=[root/path, root/(path+'.html'), root/path/'index.html']
    for f in candidates:
        if f.is_file() and f.suffix=='.html' and f.resolve().is_relative_to(root.resolve()):
            return f.relative_to(root).as_posix()
    return None

def find_existing(group, query_items, inventory, root=ROOT):
    """Prefer observed real landing pages over guessed title/slug similarity."""
    weighted={}
    for item in query_items:
        for url in item.get('landing_pages', []):
            path=resolve_landing(url,root)
            if path:
                weighted[path]=weighted.get(path,0)+item['impressions']
    observed=sorted(weighted,key=lambda p:(-weighted[p],p))
    evidence=[{'path':p,'reason':'observed_search_console_landing_page','impressions':weighted[p]} for p in observed[:4]]
    groupwords=tokens(GROUPS[group][0])
    candidates=[]
    for obj in inventory:
        words=obj['tokens']; overlap=len(words & groupwords)
        if overlap>=2 or (group=='regularization_processing' and {'tarda','regularizacion'} <= words):
            candidates.append((overlap,obj['path'],obj['draft']))
    for overlap,path,is_draft in sorted(candidates,key=lambda x:(-x[0],x[2],x[1]))[:8]:
        if path not in {v['path'] for v in evidence}:
            evidence.append({'path':path,'reason':'slug_similarity_only_manual_review','draft':is_draft})
    return evidence[:7]

def cluster_rows(rows, inventory=None, root=ROOT):
    """Accept real GSC raw rows OR prior v1 analyzed rows, for historical preview."""
    inventory=inventory if inventory is not None else existing_index(root)
    groups={}
    excluded=[]
    for row in rows:
        keys=row.get('keys',[])
        query = keys[0] if keys else row.get('query','')
        if not isinstance(query,str) or not query.strip():continue
        reason=discard_reason(query)
        if reason:
            excluded.append({'query':query,'reason':reason}); continue
        group=cluster_for(query)
        if group is None:continue
        try:
            imp=max(0,int(row.get('impressions',0)))
            clicks=max(0,int(row.get('clicks',0)))
            pos=max(0,float(row.get('position',row.get('average_position',0))))
        except (ValueError,TypeError):continue
        if not imp:continue
        urls=keys[1:2] if len(keys)>1 else row.get('landing_pages',[])
        g=groups.setdefault(group,{'id':group,'title':GROUPS[group][0], 'topic':GROUPS[group][1],
                                   'impressions':0,'clicks':0,'weighted_position':0.,'queries':{},'landing_pages':set()})
        qnorm=norm(query).strip()
        qitem=g['queries'].setdefault(qnorm,{'query':query,'impressions':0,'clicks':0,'weighted_position':0.,'landing_pages':set()})
        g['impressions']+=imp;g['clicks']+=clicks;g['weighted_position']+=pos*imp
        qitem['impressions']+=imp;qitem['clicks']+=clicks;qitem['weighted_position']+=pos*imp
        for url in urls:
            if isinstance(url,str):g['landing_pages'].add(url);qitem['landing_pages'].add(url)
    output=[]
    for group,g in groups.items():
        qs=sorted(g['queries'].values(),key=lambda x:-x['impressions'])
        query_items=[{'query':q['query'],'impressions':q['impressions'],'clicks':q['clicks'],
                      'average_position':round(q['weighted_position']/q['impressions'],1),
                      'landing_pages':sorted(q['landing_pages'])} for q in qs]
        imp=g['impressions'];position=g['weighted_position']/imp
        found=find_existing(group,query_items,inventory,root)
        published=[e for e in found if not e.get('draft')]
        observed=[e for e in published if e['reason']=='observed_search_console_landing_page']
        has_draft=any(e.get('draft') for e in found)
        # Read-only triage: prefer improving known landing pages. Never create
        # an article automatically, even if there are no matching URLs.
        if observed: action='improve_existing_page' if imp>=5 else 'monitor_existing_page'
        elif published:action='review_existing_coverage' if imp>=10 else 'monitor'
        elif has_draft: action='review_existing_draft' if imp>=10 else 'monitor'
        else:action='propose_new_article_for_review' if imp>=20 else 'monitor'
        # Impression confidence, ranking feasibility and topical priority.
        demand=min(40, 10*__import__('math').log1p(imp))
        rank=28 if 4<=position<=20 else 14 if 20<position<=60 else 6
        focus=24 if group in ('post_regularization_renewal','residence_renewal','nationality_requirements') else 16
        proof=10 if observed else 3
        score=round(demand+rank+focus+proof,1)
        output.append({'id':group,'title':g['title'],'topic':g['topic'],'impressions':imp,
                       'clicks':g['clicks'],'ctr':round(g['clicks']/imp,4),
                       'average_position':round(position,1), 'query_count':len(qs),
                       'representative_queries':query_items[:8],'existing_content_evidence':found,
                       'recommended_action':action, 'priority_score':score,
                       'legal_review_required':True,'verification_status':'NOT_VERIFIED',
                       'editorial_notes':'Confirm current BOE and official ministry guidance before rewriting or publishing.'})
    return sorted(output,key=lambda x:(-x['priority_score'],-x['impressions'],x['id'])),excluded

def make_calendar(clusters, max_items=12):
    calendar=[]
    for c in clusters:
        if c['recommended_action'] in ('monitor','monitor_existing_page'):continue
        calendar.append({'rank':len(calendar)+1,'cluster':c['title'],
                         'recommended_action':c['recommended_action'],
                         'priority_score':c['priority_score'],'impressions':c['impressions'],
                         'existing_page':next((e['path'] for e in c['existing_content_evidence'] if e['reason']=='observed_search_console_landing_page'),None),
                         'editorial_task':('Review content against official law, improve title and answer the grouped queries; preserve URL and canonical.'
                                          if c['recommended_action']=='improve_existing_page' else
                                          'Review related published pages and drafts before proposing anything new.'),
                         'requires_human_approval':True})
        if len(calendar)>=max_items:break
    return calendar

def editorial_text(clusters, calendar, metadata, period):
    source=metadata.get('source','unknown')
    lines=['# Lex Go Trámite — SEO Intelligence v2','',
           f'Source: **{source}** | Primary reporting window: **{period} days**','',
           'Read-only recommendations. Search Console impressions are not overall Google search volume.',
           'Overlapping reporting windows must not be added together. Legal accuracy and editorial approval required.','',
           '## Ranked editorial calendar','',
           '| Priority | Cluster | Impressions | Action | Existing landing page |',
           '|---:|---|---:|---|---|']
    for item in calendar:
        lines.append(f"| {item['rank']} | {item['cluster']} | {item['impressions']} | {item['recommended_action']} | {item['existing_page'] or '—'} |")
    if not calendar:lines.append('| — | No review-ready opportunity | — | Monitor | — |')
    lines.extend(['','## Query clusters',''])
    for c in clusters[:20]:
        lines.extend([f"### {c['title']}",
                      f"- {c['impressions']} impressions; {c['clicks']} clicks; position {c['average_position']}; score {c['priority_score']}",
                      f"- Action: **{c['recommended_action']}** (editorial and legal review mandatory)",
                      '- Representative searches: '+', '.join(q['query'] for q in c['representative_queries'][:5]),
                      '- Matching evidence: '+(', '.join(e['path']+' ('+e['reason']+')' for e in c['existing_content_evidence'][:3]) if c['existing_content_evidence'] else 'none located'),
                      ''])
    lines.extend(['## Guardrails','',
                  '- No editing, drafting, publishing or Git commits occur in this workflow.',
                  '- Rival-brand and location-specific professional queries are filtered conservatively; review exclusions manually.',
                  '- Similarity matching is only a prompt for editorial inspection, not a guarantee of duplicate content.',
                  '- Verify content with BOE, Inclusion/Extranjería and Ministerio de Justicia as applicable.',
                  '- Verify current legal procedures and transitional provisions before discussing mass-regularization renewals.',''])
    return '\n'.join(lines)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-json',type=Path,help='Offline fixture or historical v1 report JSON (no API call)')
    p.add_argument('--out',type=Path,default=ROOT/'reports'/'seo_intelligence.json')
    args=p.parse_args(argv)
    if args.input_json:
        raw=json.loads(args.input_json.read_text(encoding='utf8'))
        if isinstance(raw,dict) and 'windows' in raw:
            windows=raw['windows'];metadata=dict(raw.get('metadata',{}))
            metadata['source']='historical_v1_report_preview';metadata['verified_google_data']=False
            metadata['note']='Derived from previously aggregated Search Console output; refresh with live API for current data.'
        else:
            windows=raw if isinstance(raw,dict) else {'28':raw}
            metadata={'source':'offline_fixture','verified_google_data':False}
    else:
        windows,metadata=fetch_live();metadata['verified_google_data']=True
    inventory=existing_index()
    reports={}; exclusions={}
    for key,rows in windows.items():
        if not isinstance(rows,list):continue
        reports[str(key)],exclusions[str(key)]=cluster_rows(rows,inventory)
    period='28' if reports.get('28') else '90' if reports.get('90') else next(iter(reports),'28')
    selected=reports.get(period,[])
    calendar=make_calendar(selected)
    result={'version':2,'metadata':metadata,'windows':reports,'excluded_queries':exclusions,
            'editorial_calendar':calendar,'safety':'READ ONLY: no drafts, HTML, publishing state or sitemap are edited.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    args.out.with_suffix('.md').write_text(editorial_text(selected,calendar,metadata,period),encoding='utf8')
    print(f"SEO v2: {len(selected)} clusters; {len(calendar)} proposed review tasks; no website changes")
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        print(f'SEO analysis unavailable: {exc}', file=sys.stderr)
        sys.exit(2)
