#!/usr/bin/env python3
"""Non-publishing v4: creates source-evidence bundles and preview HTML from v3 briefs.

Never writes into blog/, drafts/, sitemap.xml, or publication state.
Official source fetching is best-effort, fail-closed; cannot verify legal correctness.
"""
import argparse
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

try:
    from v4_validate import is_official
except ImportError:
    from scripts.v4_validate import is_official

SOURCE_MAP = {
    'residence_renewal': [
        ('BOE - Reglamento de Extranjería (Real Decreto 1155/2024)', 'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099'),
        ('Ministerio de Inclusión', 'https://www.inclusion.gob.es/')],
    'legal_residence': [
        ('BOE - Reglamento de Extranjería (Real Decreto 1155/2024)', 'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099'),
        ('Ministerio de Inclusión', 'https://www.inclusion.gob.es/')],
    'regularization_processing': [
        ('Ministerio de Inclusión', 'https://www.inclusion.gob.es/'),
        ('BOE - Legislación vigente', 'https://www.boe.es/')],
    'long_term_residence': [
        ('BOE - Reglamento de Extranjería (Real Decreto 1155/2024)', 'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099')],
    'nationality': [
        ('BOE - Código Civil', 'https://www.boe.es/buscar/act.php?id=BOE-A-1889-4763'),
        ('Ministerio de Justicia', 'https://www.mjusticia.gob.es/')]
}

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(); self.buff=[]; self.ignore=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','noscript'): self.ignore+=1
    def handle_endtag(self, tag):
        if tag in ('script','style','noscript') and self.ignore:self.ignore-=1
        if tag in ('p','li','h1','h2','h3'): self.buff.append('\n')
    def handle_data(self,data):
        if not self.ignore: self.buff.append(data)

def fetch(url, timeout=15):
    if not is_official(url): raise ValueError('Non-approved URL')
    request=Request(url, headers={'User-Agent':'LexGoTramite-SEO-Research/1.0 (+https://lexgotramite.com)', 'Accept':'text/html'})
    with urlopen(request, timeout=timeout) as response:
        resolved=response.geturl()
        if not is_official(resolved): raise ValueError('Redirect to unapproved domain')
        if 'text/html' not in response.headers.get('Content-Type','').lower(): raise ValueError('Not an HTML source')
        raw=response.read(850_000)
        encoding=response.headers.get_content_charset() or 'utf-8'
        html=raw.decode(encoding,'replace')
    p=TextExtractor();p.feed(html)
    text=re.sub(r'[ \t]+',' ', ''.join(p.buff))
    text=re.sub(r'\n{3,}','\n\n',text).strip()
    if len(text)<250: raise ValueError('Source text too short')
    return {'url':resolved,'retrieved_at':datetime.now(timezone.utc).isoformat(),'sample':text[:2800], 'length':len(text), 'fetch_status':'retrieved_not_legally_verified'}

def build(proposals, out, fetcher=fetch):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    results=[]
    for item in proposals[:4]:
        slug=re.sub('[^a-z0-9-]','',str(item.get('id','proposal')).lower())[:70] or 'proposal'
        sources=[]
        for title,url in SOURCE_MAP.get(item.get('cluster_id'), SOURCE_MAP['legal_residence']):
            try: evidence=fetcher(url); evidence.update({'title':title})
            except Exception as ex: evidence={'title':title,'url':url,'fetch_status':'unavailable','error':str(ex)[:250]}
            sources.append(evidence)
        title=item.get('proposed_title','Propuesta editorial')
        sections=item.get('sections_to_research',[])
        questions=item.get('faq_questions',[])
        display_sources=''.join(f'<li><a href="{escape(s["url"],quote=True)}" rel="noopener">{escape(s["title"])}</a> — estado: {escape(s["fetch_status"])}</li>' for s in sources)
        # Explicit placeholders prevent preview being mistaken for legally validated content.
        document=f'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><title>VISTA PREVIA — {escape(title)}</title><meta name="description" content="{escape(item.get('proposed_meta_description',''),quote=True)}"></head>
<body><main><strong>VISTA PREVIA — NO PUBLICAR: requiere investigación jurídica y verificación independiente</strong>
<h1>{escape(title)}</h1><p>{escape(item.get('intro_draft',''))}</p>
<h2>Plan de investigación</h2><ul>{''.join('<li>'+escape(s)+'</li>' for s in sections)}</ul>
<h2>Preguntas que debe resolver el artículo</h2><ul>{''.join('<li>'+escape(q)+'</li>' for q in questions)}</ul>
<h2>Fuentes oficiales para verificar</h2><ul>{display_sources}</ul>
<p>Los enlaces y los fragmentos recuperados no prueban por sí solos los requisitos legales ni la actualidad de cada afirmación.</p>
</main></body></html>'''
        (out/f'{slug}.preview.html').write_text(document,encoding='utf-8')
        (out/f'{slug}.evidence.json').write_text(json.dumps({'proposal_id':slug,'sources':sources,'legal_claims_verified':False,'publication_allowed':False},ensure_ascii=False,indent=2),encoding='utf-8')
        results.append({'id':slug,'preview':f'{slug}.preview.html','sources_retrieved':sum(x['fetch_status']=='retrieved_not_legally_verified' for x in sources),'sources_attempted':len(sources),'publishable':False})
    summary={'version':4,'mode':'NON_PUBLISHING_PREVIEW','publication_allowed':False,'generated_at':datetime.now(timezone.utc).isoformat(),'proposals':results}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'README.md').write_text('# Lex Go Trámite — v4 preview\n\n**No content was published.** Files are research previews. Official URLs were fetched when possible, but legal claims have NOT been independently checked against their underlying provisions. Do not upload preview HTML to the live website.\n',encoding='utf-8')
    return summary

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--proposals',default='reports/editorial_v3/proposals.json');parser.add_argument('--output',default='reports/seo_v4_preview');a=parser.parse_args()
    path=Path(a.proposals)
    if not path.exists(): sys.exit('Missing v3 proposals; run SEO Intelligence v3 first')
    source=json.loads(path.read_text(encoding='utf-8'))
    if source.get('version')!=3 or not source.get('proposals'): sys.exit('Invalid v3 proposals')
    print(json.dumps(build(source['proposals'],a.output),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
