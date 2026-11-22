#!/usr/bin/env python3
"""SEO Intelligence v3: supervised, non-publishable Spanish editorial proposals.

Reads the v2 JSON report and existing repository files. Never writes to site
HTML, drafts/, sitemap, Git, publication state, or any external service.
Outputs proposal JSON/Markdown under reports/editorial_v3/ only.
"""
import argparse
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, unquote

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://lexgotramite.com'
OFFICIAL_SOURCE_STARTING_POINTS = {
    'nationality': [('Ministerio de Justicia — Nacionalidad', 'https://www.mjusticia.gob.es/'),
                    ('BOE — legislación vigente', 'https://www.boe.es/')],
    'default': [('BOE — legislación vigente', 'https://www.boe.es/'),
                ('Ministerio de Inclusión — Extranjería', 'https://www.inclusion.gob.es/')],
}

TEMPLATES = {
    'residence_renewal': {
        'title': 'Renovar la residencia en España: qué comprobar antes de iniciar el trámite',
        'description': 'Guía para entender qué autorización tienes y qué debes comprobar antes de renovar o modificar tu residencia en España.',
        'sections': ['Identifica tu autorización actual', 'Renovación, modificación u otro procedimiento: diferencias que debes verificar', 'Documentación y requisitos según tu supuesto', 'Plazos y presentación: dónde comprobarlos', 'Qué hacer ante un requerimiento o denegación'],
        'questions': ['¿Puedo renovar mi autorización actual?', '¿Qué ocurre si cambia mi situación laboral?', '¿Cómo sé qué plazo se aplica a mi expediente?'],
    },
    'legal_residence': {
        'title': 'Residencia legal en España: tipos de autorización y requisitos a consultar',
        'description': 'Conoce las principales preguntas sobre residencia legal en España y cómo localizar el procedimiento aplicable a tu caso.',
        'sections': ['Qué significa disponer de una autorización de residencia', 'Qué autorización encaja con cada situación', 'Documentos, condiciones y organismos competentes', 'Cómo comprobar la normativa vigente', 'Errores frecuentes al confundir residencia y estancia'],
        'questions': ['¿Qué tipo de autorización debo consultar?', '¿Qué documentos dependen de mi situación?', '¿Cómo compruebo los requisitos actualizados?'],
    },
    'regularization_processing': {
        'title': 'Regularización extraordinaria: cómo consultar el expediente y entender los plazos',
        'description': 'Qué comprobar al consultar el estado de una solicitud de regularización extraordinaria y dónde encontrar información oficial actualizada.',
        'sections': ['Cómo localizar el estado de tu expediente', 'Plazos: qué fuente oficial consultar', 'Requerimientos de documentación', 'Qué hacer cuando no hay novedades', 'Pasos posteriores a una resolución'],
        'questions': ['¿Dónde puedo consultar el estado de mi solicitud?', '¿Cuánto tarda la resolución según el procedimiento aplicable?', '¿Qué hago si recibo un requerimiento?'],
    },
    'long_term_residence': {
        'title': 'Residencia de larga duración: requisitos y trámites que conviene distinguir',
        'description': 'Preguntas habituales sobre residencia de larga duración, su documentación y la diferencia entre autorización y tarjeta.',
        'sections': ['Qué trámite necesitas realmente', 'Autorización de larga duración frente a documentación física', 'Requisitos y documentación a verificar', 'Presentación y seguimiento', 'Casos especiales y problemas frecuentes'],
        'questions': ['¿Debo renovar la autorización o la tarjeta?', '¿Qué requisitos debo revisar?', '¿Dónde consulto mi procedimiento?'],
    },
    'nationality': {
        'title': 'Nacionalidad española por residencia: requisitos y pasos a verificar',
        'description': 'Orientación inicial sobre nacionalidad española por residencia: períodos, documentación, pruebas y estado del expediente.',
        'sections': ['Quién puede solicitarla y qué residencia computa', 'Documentación que hay que verificar', 'Pruebas y posibles dispensas', 'Presentación y estado del expediente', 'Qué ocurre después de la concesión'],
        'questions': ['¿Cuántos años de residencia necesito en mi caso?', '¿Qué documentos deben legalizarse o traducirse?', '¿Cómo puedo consultar mi expediente?'],
    },
}

class PageMeta(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ''
        self.description = ''
        self.links = []
        self._title = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'title': self._title = True
        if tag == 'meta' and a.get('name', '').lower() == 'description': self.description = a.get('content', '')
        if tag == 'a' and a.get('href'): self.links.append(a['href'])
    def handle_endtag(self, tag):
        if tag == 'title': self._title = False
    def handle_data(self, data):
        if self._title: self.title += data

def load_page(root, name):
    """Only existing HTML inside the site; never read arbitrary paths from GSC."""
    if not isinstance(name, str) or not name.endswith('.html'): return None
    p = (root / name).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file(): return None
    meta = PageMeta()
    meta.feed(p.read_text(encoding='utf-8'))
    return {'path': name, 'title': meta.title.strip(), 'description': meta.description.strip(), 'links': meta.links}

def internal_target(root, href):
    parts = urlsplit(href.strip())
    if parts.scheme not in ('', 'https', 'http') or (parts.netloc and parts.hostname not in ('lexgotramite.com', 'www.lexgotramite.com')):
        return None
    if not parts.path or parts.path.startswith('//'): return None
    name = unquote(parts.path.lstrip('/'))
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()): return None
    attempts = [path] if path.suffix else [Path(str(path) + '.html'), path / 'index.html']
    if name == '/': attempts = [root / 'index.html']
    for candidate in attempts:
        if candidate.is_file() and candidate.suffix == '.html' and candidate.is_relative_to(root.resolve()):
            return candidate.relative_to(root).as_posix()
    return None

def select_related(root, existing, cluster_id, limit=3):
    candidate_paths = {
        'residence_renewal': ['residencia-espana.html','blog/renovacion-despues-del-ano-regularizacion.html','nacionalidad-espanola.html'],
        'legal_residence': ['residencia-espana.html','blog/renovar-residencia-espana.html','nacionalidad-espanola.html'],
        'regularization_processing': ['regularizacion-espana-2026.html','blog/renovacion-despues-del-ano-regularizacion.html','residencia-espana.html'],
        'long_term_residence': ['residencia-espana.html','blog/renovar-residencia-espana.html','nacionalidad-espanola.html'],
        'nationality': ['nacionalidad-espanola.html','residencia-espana.html'],
    }.get(cluster_id, ['residencia-espana.html','nacionalidad-espanola.html'])
    result=[]
    for path in candidate_paths:
        if path == existing: continue
        page = load_page(root, path)
        if not page: continue
        url = '/' + path.removesuffix('.html')
        result.append({'path': path, 'url': url, 'suggested_anchor': page['title'][:95] or path.removesuffix('.html').replace('-', ' '), 'verification': 'check live URL and contextual relevance before adding'})
        if len(result) >= limit: break
    return result

def detect_template(cluster):
    id_ = str(cluster.get('id',''))
    if id_ in TEMPLATES: return id_
    label = (str(cluster.get('title','')) + ' ' + id_).lower()
    if 'nacional' in label: return 'nationality'
    if 'larga duraci' in label: return 'long_term_residence'
    if 'renov' in label: return 'residence_renewal'
    if 'plazo' in label or 'regularizaci' in label: return 'regularization_processing'
    return 'legal_residence'

def safe_file_id(text):
    name = re.sub('[^a-z0-9-]+', '-', text.lower()).strip('-')
    return name[:65] or 'topic'

def markdown_escape(text):
    return str(text).replace('|', '\\|').replace('\n', ' ').replace('\r', ' ')

def create_proposal(item, group, root, metadata):
    template_id = detect_template(group)
    template = TEMPLATES[template_id]
    target = item.get('existing_page')
    existing = load_page(root, target)
    action = 'improve_existing_page' if existing else 'new_draft_for_review'
    # If the v2 report says an existing page exists but this checkout doesn't contain it,
    # never silently propose a duplicate new article.
    if target and not existing: action = 'manual_review_missing_existing_page'
    queries = group.get('representative_queries', [])[:8]
    legal_topic = 'nationality' if template_id == 'nationality' else 'default'
    return {
        'id': f"{item['rank']:02d}-{safe_file_id(str(group.get('id') or template_id))}",
        'status': 'AWAITING_HUMAN_LEGAL_AND_EDITORIAL_APPROVAL',
        'publication_allowed': False,
        'action': action,
        'cluster': group.get('title', item.get('cluster','')),
        'cluster_id': group.get('id'),
        'rank': item.get('rank'),
        'score': item.get('priority_score'),
        'impressions_28d': group.get('impressions'),
        'clicks_28d': group.get('clicks'),
        'source_data_end_date': metadata.get('data_end_date'),
        'source_type': metadata.get('source'),
        'queries': [q.get('query') for q in queries if q.get('query')],
        'target_page': target if existing else None,
        'existing_page_title': existing['title'] if existing else None,
        'existing_meta_description': existing['description'] if existing else None,
        'proposed_title': template['title'],
        'proposed_meta_description': template['description'],
        'intro_draft': f"Esta guía responde a las dudas más habituales sobre {str(group.get('title','este trámite')).lower()}. El procedimiento aplicable depende de la autorización y de las circunstancias de cada persona; antes de actuar, comprueba la información oficial vigente.",
        'sections_to_research': template['sections'],
        'faq_questions': template['questions'],
        'related_internal_links': select_related(root, target, template_id),
        'official_sources_to_verify': [{'label':a, 'url':b, 'verified':False} for a,b in OFFICIAL_SOURCE_STARTING_POINTS[legal_topic]],
        'required_checks': [
            'Verify every deadline, requirement and procedure in currently applicable official law or guidance.',
            'Verify exact citations and dates; add evidence for each substantive legal statement.',
            'Compare with the existing article and related content to avoid keyword cannibalization.',
            'Confirm proposed internal links resolve in production before insertion.',
            'Review editorial quality, contact CTA, authorship and accessibility.',
            'Obtain explicit human legal and editorial approval before changing production content.'
        ],
    }

def render_markdown(p):
    lines = [f"# BORRADOR PARA REVISIÓN — {p['proposed_title']}", '',
             '**NO PUBLICAR. Pendiente de verificación jurídica y aprobación editorial.**', '',
             f"- Acción propuesta: `{p['action']}`",
             f"- Página existente: `{p['target_page'] or 'No verificada'}`",
             f"- Impresiones 28 días (grupo): {p['impressions_28d']}",
             f"- Prioridad: {p['score']}",
             f"- Datos hasta: {p['source_data_end_date']}", '',
             '## SEO propuesto', '',
             f"- Título: {p['proposed_title']}",
             f"- Meta descripción: {p['proposed_meta_description']}", '',
             '## Introducción propuesta (no contiene asesoramiento legal específico)', '',
             p['intro_draft'], '',
             '## Esquema de contenido — completar tras verificar fuentes', '']
    for section in p['sections_to_research']:
        lines += [f'### {section}', '', '[PENDIENTE: texto jurídicamente verificado, con fuente oficial concreta y fecha de consulta.]', '']
    lines += ['## Preguntas frecuentes sugeridas', '']
    for q in p['faq_questions']:
        lines += [f'### {q}', '', '[PENDIENTE: respuesta verificada; no publicar marcador.]', '']
    lines += ['## Enlaces internos sugeridos (comprobar URL pública)', '']
    for l in p['related_internal_links']:
        lines.append(f"- [{l['suggested_anchor']}]({l['url']}) — revisar pertinencia")
    lines += ['', '## Fuentes oficiales por verificar', '']
    for source in p['official_sources_to_verify']:
        lines.append(f"- {source['label']}: {source['url']} (NO VERIFICADA)")
    lines += ['', '## Consultas de Search Console', '']
    lines += [f'- {markdown_escape(q)}' for q in p['queries']]
    lines += ['', '## Aprobaciones necesarias', '', '- [ ] Verificación jurídica y de fuentes', '- [ ] Revisión editorial y SEO', '- [ ] Comprobación de links/canonical en preview', '- [ ] Aprobación explícita antes de publicar', '']
    return '\n'.join(lines)

def generate(data, root, limit=5):
    if data.get('version') != 2: raise ValueError('Expected a v2 SEO Intelligence report.')
    metadata=data.get('metadata',{})
    if metadata.get('source') not in ('google_search_console_api', 'offline_fixture'):
        raise ValueError('Unknown report source.')
    groups = {g.get('id'): g for g in data.get('windows',{}).get('28',[]) if isinstance(g,dict)}
    proposals=[]
    for item in data.get('editorial_calendar',[])[:limit]:
        if not isinstance(item,dict): continue
        group=groups.get(item.get('cluster'))
        if group is None:
            # v2 calendar uses the label, while the windows use the stable id.
            group=next((g for g in groups.values() if g.get('title')==item.get('cluster')),None)
        if group is None: continue
        proposals.append(create_proposal(item,group,root,metadata))
    return {'version':3, 'generated_on':date.today().isoformat(), 'input_metadata':metadata,
            'publication_allowed':False, 'workflow':'READ_ONLY_REVIEW_PACK',
            'proposals':proposals}

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',type=Path,default=DEFAULT_ROOT/'reports/seo_intelligence.json')
    ap.add_argument('--output',type=Path,default=DEFAULT_ROOT/'reports/editorial_v3')
    ap.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    ap.add_argument('--limit',type=int,default=5)
    a=ap.parse_args(argv)
    if not (1 <= a.limit <= 20): ap.error('limit must be between 1 and 20')
    if not a.input.is_file(): ap.error('v2 report missing; run SEO Intelligence first')
    root=a.root.resolve()
    data=json.loads(a.input.read_text(encoding='utf-8'))
    result=generate(data,root,a.limit)
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'proposals.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary=['# Lex Go Trámite — propuestas SEO v3', '',
             '**REVISIÓN OBLIGATORIA — NINGÚN ARCHIVO ES PUBLICABLE AUTOMÁTICAMENTE**','',
             f"Origen de datos: {result['input_metadata'].get('source')}",'',
             '| Prioridad | Oportunidad | Página a revisar | Acción |',
             '|---:|---|---|---|']
    for p in result['proposals']:
        (a.output/(p['id']+'.md')).write_text(render_markdown(p),encoding='utf-8')
        summary.append(f"| {p['rank']} | {markdown_escape(p['cluster'])} | `{p['target_page'] or 'por verificar'}` | {p['action']} |")
    (a.output/'README.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    print(f"Produced {len(result['proposals'])} non-publishable editorial proposals in {a.output}; website unchanged")
    return 0

if __name__=='__main__': raise SystemExit(main())
