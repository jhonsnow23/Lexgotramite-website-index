#!/usr/bin/env python3
"""Lex Go Trámite v4.1 evidence-grounded full-article draft generator.

Fail closed: never writes public pages or publication state. Legal accuracy needs
independent substantive review; exact quotes alone cannot prove legal applicability.
"""
import argparse
import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

try:
    from v4_validate import is_official
except ImportError:
    from scripts.v4_validate import is_official

BOE_LEGAL = 'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099'
BOE_NATIONALITY = 'https://www.boe.es/buscar/act.php?id=BOE-A-1889-4763'
SOURCES = {
    'residence_renewal': [('BOE-A-2024-24099', BOE_LEGAL)],
    'legal_residence': [('BOE-A-2024-24099', BOE_LEGAL)],
    'residency_options': [('BOE-A-2024-24099', BOE_LEGAL)],
    'regularization_processing': [], # A broad RD cannot establish specific 2026 processing rules
    'long_term_residence': [('BOE-A-2024-24099', BOE_LEGAL)],
    'nationality': [('BOE-A-1889-4763', BOE_NATIONALITY)],
}
SYSTEM = '''Eres redactor jurídico cuidadoso en España. Crea un artículo útil, original y completo en español europeo, EXCLUSIVAMENTE con la evidencia oficial incluida. Nunca inventes plazos, derechos, condiciones, resoluciones ni citas. Si el material no fundamenta un extremo, omite la afirmación y añade una cuestión pendiente. Debes producir SOLO un objeto JSON válido, sin markdown. Campos exactos: title (texto), meta_description (texto), introduction (un único texto con 2 párrafos separados por doble salto de línea; nunca una lista), sections (array de objetos con heading y paragraphs, array de textos), faqs (array de objetos question y answer), claims (array de objetos con claim, source_id, evidence_excerpt: cita LITERAL exacta del fragmento suministrado), unresolved_questions (array de textos). Cada afirmación jurídica concreta en los párrafos o FAQ debe tener su equivalente en claims y una cita literal CONTIGUA EXACTA del texto oficial suministrado, sin acortar, parafrasear o unir palabras. Evita afirmaciones generales basadas en normas sobre supuestos específicos. Restringe el alcance del artículo a los tipos de autorización cubiertos claramente por la evidencia; si faltan disposiciones que son necesarias para una respuesta correcta, anótalo en unresolved_questions. Nunca atribuyas revisión profesional. No sugieras que se ha publicado ni está legalmente validado.'''

class Plain(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.lines=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','nav','footer'): self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','nav','footer') and self.skip:self.skip-=1
        if tag in ('p','h1','h2','h3','li','article','section'):self.lines.append('\n')
    def handle_data(self,data):
        if not self.skip:self.lines.append(data)

def normalize(s): return ' '.join(str(s).split()).casefold()

def introductory_paragraphs(value):
    if isinstance(value, str):
        return [p.strip() for p in value.split('\n\n') if p.strip()]
    if isinstance(value, list) and all(isinstance(p, str) for p in value):
        return [p.strip() for p in value if p.strip()]
    return []

def fetch_official(url, timeout=18, opener=None):
    if not is_official(url):raise ValueError('URL does not belong to an approved official host')
    req=urllib.request.Request(url, headers={'User-Agent':'LexGoTramite OfficialSourceResearch/1.0 (https://lexgotramite.com)','Accept':'text/html,application/xhtml+xml'})
    opener=opener or urllib.request.urlopen
    with opener(req,timeout=timeout) as r:
        dest=r.geturl()
        if not is_official(dest):raise ValueError('Redirect to nonofficial host')
        if 'html' not in r.headers.get('Content-Type','').lower():raise ValueError('Unexpected content type; not parsed as HTML')
        raw=r.read(2_500_001)
        if len(raw)>2_500_000:raise ValueError('Official document exceeds safe retrieval limit')
        encoding=r.headers.get_content_charset() or 'utf-8'
    p=Plain();p.feed(raw.decode(encoding,errors='replace'))
    txt=re.sub(r'\n\s*\n+', '\n', ''.join(p.lines)).strip()
    if len(txt)<1000:raise ValueError('Insufficient document text')
    return {'url':dest,'text':txt,'fetched_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'sha256':hashlib.sha256(raw).hexdigest()}

def source_excerpt(text, needles, limit=11000):
    """Extract bounded contiguous paragraphs relevant to a topic; not arbitrary stitched claims."""
    paragraphs=[p.strip() for p in re.split(r'\n+',text) if len(p.strip())>50]
    ranked=sorted(enumerate(paragraphs), key=lambda v:(-sum(n in normalize(v[1]) for n in needles), v[0]))
    pieces=[];total=0
    for _,p in ranked:
        if total+len(p)>limit:continue
        pieces.append(p);total+=len(p)
        if total>limit*.75:break
    return '\n\n'.join(pieces)

def select_proposal(data):
    if data.get('version')!=3 or not isinstance(data.get('proposals'),list):raise ValueError('Expected v3 proposals JSON')
    for p in data['proposals']:
        if p.get('cluster_id') in SOURCES and SOURCES[p['cluster_id']] and p.get('action')=='improve_existing_page':return p
    raise ValueError('No proposal with applicable identified official legal source; no generation')

def openai_generate(proposal,sources,model='gpt-4.1-mini',endpoint='https://api.openai.com/v1/chat/completions',requester=None):
    key=os.environ.get('OPENAI_API_KEY')
    if not key:raise RuntimeError('OPENAI_API_KEY is not configured; draft not generated')
    if endpoint != 'https://api.openai.com/v1/chat/completions':raise ValueError('Unsupported API endpoint')
    evidence=[]
    for s in sources:
        evidence.append({'source_id':s['id'],'official_url':s['url'],'retrieved_at':s['fetched_at'],'official_extract':s['extract']})
    payload={'model':model,'temperature':0.2,'response_format':{'type':'json_object'}, 'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps({'topic':proposal.get('proposed_title'), 'intent':proposal.get('queries',[])[:8], 'research_sections':proposal.get('sections_to_research',[]), 'evidence':evidence},ensure_ascii=False)}]}
    b=json.dumps(payload,ensure_ascii=False).encode('utf8')
    req=urllib.request.Request(endpoint,data=b,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    requester=requester or urllib.request.urlopen
    with requester(req,timeout=85) as r:response=json.load(r)
    return json.loads(response['choices'][0]['message']['content'])

def validate_draft(draft,sources):
    errors=[]
    for fld in ['title','meta_description']:
        if not isinstance(draft.get(fld),str) or len(draft[fld].strip())<25:errors.append('Incomplete '+fld)
    intro=introductory_paragraphs(draft.get('introduction'))
    if not intro or sum(len(p) for p in intro)<70:errors.append('Incomplete introduction')
    sections=draft.get('sections',[])
    if not isinstance(sections,list) or len(sections)<3:errors.append('Fewer than three substantive sections')
    for s in sections if isinstance(sections,list) else []:
        if not isinstance(s,dict) or not s.get('heading') or not isinstance(s.get('paragraphs'),list) or not s['paragraphs']:errors.append('Malformed section')
    claims=draft.get('claims',[])
    if not isinstance(claims,list) or not claims:errors.append('No claim evidence');claims=[]
    lookup={s['id']:s for s in sources};valid=0
    for i,c in enumerate(claims):
        if not isinstance(c,dict):errors.append(f'Malformed claim {i+1}');continue
        src=lookup.get(c.get('source_id'))
        quote=c.get('evidence_excerpt','')
        if not src:errors.append(f'Claim {i+1}: unknown source id');continue
        if len(normalize(quote))<45 or normalize(quote) not in normalize(src['extract']):errors.append(f'Claim {i+1}: evidence is not an exact retrieved excerpt');continue
        if len(normalize(c.get('claim','')))<15:errors.append(f'Claim {i+1}: empty claim');continue
        valid+=1
    if draft.get('unresolved_questions'):errors.append('Outstanding legal research questions')
    text=json.dumps(draft,ensure_ascii=False)
    if re.search(r'\[PENDIENTE\]|lorem ipsum|TODO:',text,re.I):errors.append('Placeholder in generated article')
    if len(normalize(text))<1400:errors.append('Draft too short')
    return {'schema_and_evidence_checks_passed':not errors,'legal_claims_checked':len(claims),'exact_quotes_matched':valid,'errors':errors,'independent_legal_accuracy_verified':False,'publication_allowed':False,'decision_reason':'Article is an unapproved draft. Verbatim source excerpts cannot prove the correct legal interpretation or applicability.'}

def render(draft,sources,decision):
    esc=lambda t:html.escape(str(t),quote=True)
    title=esc(draft.get('title','Artículo para revisar'))
    sections=[]
    for s in draft.get('sections',[]):
        if isinstance(s,dict):sections.append('<h2>'+esc(s.get('heading',''))+'</h2>'+''.join('<p>'+esc(p)+'</p>' for p in s.get('paragraphs',[])))
    faqs=''.join('<h3>'+esc(q.get('question',''))+'</h3><p>'+esc(q.get('answer',''))+'</p>' for q in draft.get('faqs',[]) if isinstance(q,dict))
    cites=''.join('<li>'+esc(s['id'])+': <a href="'+esc(s['url'])+'" rel="noopener noreferrer">'+esc(s['url'])+'</a> (consultado: '+esc(s['fetched_at'][:10])+')</li>' for s in sources)
    return '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NO PUBLICAR — '+title+'</title><meta name="description" content="'+esc(draft.get('meta_description',''))+'"></head><body><main><p><strong>BORRADOR AUTOMÁTICO — REVISIÓN JURÍDICA PENDIENTE — PROHIBIDA LA PUBLICACIÓN</strong></p><h1>'+title+'</h1>'+''.join('<p>'+esc(p)+'</p>' for p in introductory_paragraphs(draft.get('introduction')))+''.join(sections)+'<h2>Preguntas frecuentes</h2>'+faqs+'<h2>Fuentes oficiales y normativa consultada</h2><ul>'+cites+'</ul><p>Contenido informativo sujeto a revisión; no constituye asesoramiento individualizado.</p></main></body></html>'

def run(args):
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    status={'version':'4.1','phase':'GENERATE_DRAFT','publication_allowed':False,'result':'blocked','reasons':[]}
    try:
        proposals=json.loads(Path(args.proposals).read_text(encoding='utf8'))
        proposal=select_proposal(proposals)
        status['topic']=proposal.get('proposed_title')
        sources=[];failures=[]
        needles=['renovacion','residencia','autorizacion','requisitos','prorroga'] if proposal.get('cluster_id')=='residence_renewal' else ['residencia','autorizacion','requisitos','extranjeria']
        for sid,url in SOURCES[proposal['cluster_id']]:
            try:
                r=fetch_official(url)
                excerpt=source_excerpt(r['text'],needles)
                if len(excerpt)<1200:raise ValueError('Not enough relevant legal material')
                sources.append({'id':sid,'url':r['url'],'fetched_at':r['fetched_at'],'sha256':r['sha256'],'extract':excerpt})
            except (ValueError,urllib.error.URLError,TimeoutError) as e:
                failures.append({'url':url,'error':str(e)[:200]})
        (output/'source_retrieval.json').write_text(json.dumps({'sources':[{'id':s['id'],'url':s['url'],'sha256':s['sha256'],'fetched_at':s['fetched_at'],'extract':s['extract']} for s in sources], 'failures':failures},ensure_ascii=False,indent=2),encoding='utf8')
        if failures or not sources:raise RuntimeError('Official evidence retrieval incomplete; article generation blocked')
        draft=openai_generate(proposal,sources,model=args.model)
        (output/'article.json').write_text(json.dumps(draft,ensure_ascii=False,indent=2),encoding='utf8')
        decision=validate_draft(draft,sources)
        (output/'article.preview.html').write_text(render(draft,sources,decision),encoding='utf8')
        status.update({'result':'draft_generated' if decision['schema_and_evidence_checks_passed'] else 'draft_failed_checks','validation':decision})
        if not decision['schema_and_evidence_checks_passed']:
            status['reasons'].extend(decision['errors'])
    except Exception as e:
        status['reasons'].append(str(e)[:350])
    (output/'decision.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'result':status['result'],'publication_allowed':False,'reasons':status['reasons']},ensure_ascii=False))
    # Fail CI if a draft could not be produced, but leave artifacts for troubleshooting.
    return 0 if status['result']=='draft_generated' else 1

def main():
    p=argparse.ArgumentParser();p.add_argument('--proposals',default='reports/editorial_v3/proposals.json');p.add_argument('--output',default='reports/seo_v41');p.add_argument('--model',default='gpt-4.1-mini');return run(p.parse_args())
if __name__=='__main__':sys.exit(main())
