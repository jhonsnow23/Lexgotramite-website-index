"""V5.0 legal research: topic-relevant BOE discovery. Draft-only and fail-closed.

No website/blog text is read here. Source identification != legal verification.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
import unicodedata
from collections import defaultdict

try:
    from boe_universal_v45 import BASE, api_get, _identifier, _caption, tag, retrieve, BOEError
except ImportError:
    from scripts.boe_universal_v45 import BASE, api_get, _identifier, _caption, tag, retrieve, BOEError

# Documents are discovery candidates, not universal legal authorities.
SOURCE_CANDIDATES = {
    'nationality': ['BOE-A-1889-4763','BOE-A-2015-12047'],
    'residence': ['BOE-A-2024-24099'],
    'renewal': ['BOE-A-2024-24099'],
    'arraigo': ['BOE-A-2024-24099'],
    'family': ['BOE-A-2024-24099'],
    'other': [],
}
QUESTION_SEEDS = {
 'residence': [
  ('categories','Qué categorías de autorización de residencia contempla la normativa','residencia temporal residencia larga duracion autorizacion'),
  ('differences','En qué se diferencian las categorías relevantes de residencia','residencia temporal larga duracion'),
  ('eligibility','Qué condiciones se aplican según el tipo de autorización','requisitos autorizacion residencia'),
 ],
 'nationality': [
  ('eligibility','Qué supuestos de nacionalidad por residencia contempla la ley','nacionalidad residencia concesion'),
  ('exceptions','Qué plazos y excepciones se aplican a esos supuestos','nacionalidad residencia plazo excepciones'),
  ('procedure','Cómo se tramita una solicitud de nacionalidad por residencia','procedimiento nacionalidad residencia'),
 ],
 'renewal': [
  ('scope','Qué autorización concreta se pretende renovar','renovacion autorizacion residencia'),
  ('requirements','Qué requisitos específicos se aplican','renovacion requisitos residencia'),
  ('steps','Qué trámite y plazo oficial corresponden','renovacion solicitud plazo'),
 ],
 'arraigo': [
  ('types','Qué modalidad de arraigo corresponde a la consulta','arraigo sociolaboral socioformativo social segunda oportunidad'),
  ('requirements','Qué requisitos se aplican a esa modalidad','arraigo requisitos autorizacion'),
  ('procedure','Cómo se solicita esa autorización','arraigo solicitud procedimiento'),
 ],
 'family': [
  ('scope','Cuál es el procedimiento familiar aplicable','reagrupacion familiar familiares'),
  ('requirements','Cuáles son los requisitos concretos','reagrupacion familiar requisitos'),
  ('procedure','Qué solicitud y documentación exige','reagrupacion familiar documentacion'),
 ],
}
STOP={'de','del','el','la','las','los','y','en','para','por','a','un','una','que','como','cuanto','se','es','su','con','al','espana','espanola','espanol','tipos','tipo'}

def normalize(s):
    s=''.join(c for c in unicodedata.normalize('NFKD',str(s).lower()) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+',s))

def tokens(s):
    return {t for t in normalize(s).split() if len(t)>2 and t not in STOP}

def group_of(cluster,topic):
    t=normalize(cluster+' '+topic)
    if 'nacionalidad' in t or 'nationality' in t:return 'nationality'
    if 'arraigo' in t:return 'arraigo'
    if 'reagrupacion' in t or 'family' in t:return 'family'
    if 'renov' in t or 'renew' in t:return 'renewal'
    if 'residen' in t:return 'residence'
    return 'other'

def questions(group):
    return [{'id':a,'question':b,'query':c,'status':'NOT_ANSWERED','evidence_ids':[]} for a,b,c in QUESTION_SEEDS.get(group,[])]

def score_title(title,query):
    a=tokens(title);b=tokens(query)
    if not a or not b:return 0
    matches=len(a & b)
    # A generic index heading such as 'Articulo 2' is not evidence of relevance.
    return matches/len(b) if matches>=1 else 0

def parse_index_titles(root):
    """Use verified label and block-ID pairing from the actual BOE index.
    No assumption that article number equals block ID.
    """
    out={}
    for n in root.iter():
        if tag(n) not in ('bloque','item','elemento','entrada','registro','precepto','articulo','artículo'):continue
        bid=_identifier(n);caption=_caption(n)
        if not bid or not caption:continue
        match=re.search(r'\bArt(?:[íi]culo|\.)?\s+(\d{1,4})(?:\s*(bis|ter|qu[aá]ter))?\b',caption,re.I)
        if not match:continue
        num=(int(match.group(1)),(match.group(2) or '').lower())
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,90}',bid):continue
        key=(num[0],num[1]);pair=(bid,caption)
        if key in out and out[key]!=pair:
            # Ambiguous mapping: omit this particular article rather than guess.
            out[key]=None
        elif key not in out:out[key]=pair
    return [(str(k[0])+(k[1] or ''),v[0],v[1]) for k,v in out.items() if v is not None]

def contextual_index(root):
    """Pair article entries with official preceding index section headings.

    A section heading is a search hint only. It is NOT claim evidence, and every
    retrieved block still requires independent relevance and legal review.
    """
    articles=parse_index_titles(root)
    known={(num,bid):title for num,bid,title in articles}
    contexts={};headings=[]
    section_names={'libro','titulo','título','capitulo','capítulo','seccion','sección','subseccion','subsección','parte'}
    for n in root.iter():
        if tag(n) not in ('bloque','item','elemento','entrada','registro','precepto','articulo','artículo'):
            continue
        bid=_identifier(n);title=_caption(n)
        if not title or not bid:continue
        lowered=normalize(title)
        if (re.match(r'^(libro|titulo|capitulo|seccion|subseccion|parte)\s+',lowered)
                and 'art ' not in lowered[:8]):
            level=next((x for x in ('libro','titulo','capitulo','seccion','subseccion','parte') if lowered.startswith(x+' ')),None)
            order=['parte','libro','titulo','capitulo','seccion','subseccion']
            idx=order.index(level) if level in order else len(order)-1
            headings=[(i,h) for i,h in headings if i<idx]
            headings.append((idx,title))
            continue
        number_match=re.search(r'\bArt(?:[íi]culo|\.)?\s+(\d{1,4})(?:\s*(bis|ter|qu[aá]ter))?\b',title,re.I)
        if number_match:
            number=number_match.group(1)+(number_match.group(2) or '').lower()
            if (number,bid) in known:
                contexts[(number,bid)]=' '.join(h for _,h in headings)
    return [(num,bid,title,contexts.get((num,bid),'')) for num,bid,title in articles]


def discover(group,topic,*,index_fetch=api_get,max_per_source=8):
    """Discover candidate articles using *real* index headings, never by ordinal position.

    Return candidate source/article pairs with per-question heading relevance.
    Short generic article headings may not reveal the provision subject: in that
    case return no evidence and fail closed rather than picking articles 1-2.
    """
    found=[];diagnostics=[]
    qs=questions(group)
    for doc in SOURCE_CANDIDATES.get(group,[]):
        endpoint=BASE+doc+'/texto/indice'
        try:
            root,_=index_fetch(endpoint)
            rows=contextual_index(root)
            candidates=[]
            for number,bid,title,context in rows:
                relevance={q['id']:score_title(title+' '+context,q['query']+' '+topic) for q in qs}
                value=max(relevance.values(),default=0)
                if value>0:candidates.append({'source_id':doc,'article':number,'block_id':bid,'title':title,'section_context':context,'score':value,'question_scores':relevance})
            candidates.sort(key=lambda x:(-x['score'],x['article']))
            found.extend(candidates[:max_per_source])
            diagnostics.append({'document':doc,'index_articles':len(rows),'qualified_candidates':len(candidates)})
        except Exception as e:
            diagnostics.append({'document':doc,'error':type(e).__name__,'detail':str(e)[:180]})
    return found,diagnostics

def coverage(questions_list,evidence,*,semantic_judgments=None):
    """Fail-closed: lexical relevance never establishes legal sufficiency.
    An explicit independent judgment may note coverage for draft preparation,
    but not legally certify current applicability or publication.
    """
    judgments=semantic_judgments or {}
    result=[]
    for q in questions_list:
        j=judgments.get(q['id'],{})
        ids=[r for r in j.get('evidence_ids',[]) if r in {x['evidence_id'] for x in evidence}]
        status=j.get('status','NOT_ANSWERED')
        if status not in ('ANSWERED_WITH_EVIDENCE','PARTIALLY_ANSWERED','NOT_ANSWERED','REQUIRES_LEGAL_INTERPRETATION','SOURCE_UNAVAILABLE'):
            status='NOT_ANSWERED'
        if status=='ANSWERED_WITH_EVIDENCE' and not ids:status='NOT_ANSWERED'
        result.append({**q,'status':status,'evidence_ids':ids,'reason':str(j.get('reason',''))[:400]})
    return result,all(x['status']=='ANSWERED_WITH_EVIDENCE' for x in result) and bool(result)

def metadata_duplicate(proposal):
    """No legacy blog bodies are opened. Conservatively skip possible duplicates."""
    return bool(proposal.get('existing_pages') or proposal.get('existing_page') or proposal.get('action') in ('improve_existing_page','IMPROVE_EXISTING_ARTICLE'))
