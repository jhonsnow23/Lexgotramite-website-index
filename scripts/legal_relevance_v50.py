"""V5.0 legal research: topic-relevant BOE discovery. Draft-only and fail-closed.

No website/blog text is read here. Source identification != legal verification.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
import unicodedata
from collections import defaultdict
from itertools import islice

try:
    from boe_universal_v45 import BASE, api_get, _identifier, _caption, tag, txt, _number_of, retrieve, BOEError
except ImportError:
    from scripts.boe_universal_v45 import BASE, api_get, _identifier, _caption, tag, txt, _number_of, retrieve, BOEError

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

# Query expansion is a discovery aid, never a statement of legal equivalence.
# Each cluster is deliberately distinct: TIE renewal != renewal of status.
CONCEPT_GROUPS = {
 'renewal': {
  'long_term_status': ('larga duracion', 'residencia larga duracion', 'permanente', 'autorizacion'),
  'identity_card': ('tarjeta identidad extranjero', 'tie', 'documentacion extranjero', 'tarjeta', 'renovacion tarjeta'),
  'procedure': ('renovacion', 'vigencia', 'solicitud', 'procedimiento', 'documentacion', 'expedicion'),
 },
 'residence': {
  'categories': ('residencia temporal','residencia larga duracion','autorizacion residencia', 'circunstancias excepcionales'),
  'requirements': ('requisitos','concesion','trabajo','reagrupacion familiar'),
 },
 'nationality': {
  'nationality': ('nacionalidad','naturalizacion','adquisicion','residencia'),
  'procedure': ('solicitud','expediente','procedimiento','requisitos'),
 },
 'arraigo': {
  'arraigo': ('arraigo','circunstancias excepcionales','sociolaboral','socioformativo','social'),
  'procedure': ('solicitud','requisitos','autorizacion','residencia'),
 },
 'family': {
  'family': ('reagrupacion familiar','familiares','familiar','residencia'),
  'procedure': ('requisitos','solicitud','documentacion'),
 },
}

def score_title(title,query):
    """Conservative lexical discovery score; never certifies claim relevance."""
    a=tokens(title);b=tokens(query)
    if not a or not b:return 0
    return len(a & b)/len(b)

def _label(n):
    """Read actual BOE index records, including nested title/epigraph elements."""
    caption=_caption(n)
    if caption:return caption
    for child in n:
        if tag(child) in ('titulo','título','rotulo','rótulo','epigrafe','epígrafe','nombre','caption','texto'):
            content=txt(child)
            if content:return content
    return ''

def _index_items(root):
    valid={'bloque','item','elemento','entrada','registro','precepto','articulo','artículo'}
    for n in root.iter():
        if tag(n) in valid:
            bid=_identifier(n)
            if bid and re.fullmatch(r'[A-Za-z0-9_-]{1,90}',bid):
                yield n,bid,_label(n)

def parse_index_titles(root):
    """Explicit heading identifies article. No guessed mapping from opaque IDs."""
    out={}; conflicts=set()
    for n,bid,label in _index_items(root):
        article=_number_of(label)
        if not article:
            for child in n:
                if tag(child) in ('texto','rotulo','rótulo','epigrafe','epígrafe','nombre','caption','titulo','título'):
                    article=_number_of(txt(child))
                    if article:break
        if not article:continue
        key=(int(article[0]),article[1])
        pair=(bid,label)
        if key in out and out[key][0]!=bid:conflicts.add(key)
        else:out[key]=pair
    return [(str(k[0])+(k[1] or ''),v[0],v[1]) for k,v in out.items() if k not in conflicts]

def contextual_index(root):
    """Retrieve article headings plus ordered parent headings from BOE index metadata.

    Context is for finding candidates only: the source provision text must be checked.
    """
    articles=parse_index_titles(root)
    allowed={(n,b) for n,b,_ in articles}
    contexts={};heads=[]
    order=('parte','libro','titulo','capitulo','seccion','subseccion')
    for _,bid,title in _index_items(root):
        lowered=normalize(title)
        match=re.match(r'^(parte|libro|titulo|capitulo|seccion|subseccion)\b',lowered)
        if match:
            level=order.index(match.group(1))
            heads=[(l,h) for l,h in heads if l<level]+[(level,title)]
            continue
        heading=_number_of(title)
        if heading:
            number=str(heading[0])+(heading[1] or '')
            if (number,bid) in allowed:
                contexts[(number,bid)]=' '.join(h for _,h in heads)
    return [(num,bid,title,contexts.get((num,bid),'')) for num,bid,title in articles]

def _discovery_query(group,topic,q):
    concepts=CONCEPT_GROUPS.get(group,{})
    # Include query-specific concepts without falsely treating them as equivalent.
    terms=[topic,q['query']]
    terms.extend(phrase for phrases in concepts.values() for phrase in phrases)
    return ' '.join(terms)

def _candidate_score(group,topic,title,context,qs):
    concepts=CONCEPT_GROUPS.get(group,{})
    content=title+' '+context
    scores={q['id']:score_title(content,q['query']+' '+topic) for q in qs}
    semantic_hints={label: max((score_title(content,phrase) for phrase in phrases),default=0)
                    for label,phrases in concepts.items()}
    # Require a specific subject hit. General words such as "residencia" alone
    # must not cause a border-crossing article to qualify.
    content_tokens=tokens(content)
    topic_tokens=tokens(topic)
    direct=len(content_tokens & topic_tokens)
    weighted=max(scores.values(),default=0)
    strong=max(semantic_hints.values(),default=0)
    if not direct and strong<0.5:return 0,scores,semantic_hints
    return round(max(weighted,strong)*0.8+min(direct,3)*0.08,4),scores,semantic_hints

def provision_relevance(group,topic,text,question_list):
    """Deterministic subject guard for retrieved full text.

    This is a minimum exclusion check; it is not a complete semantic or legal review.
    """
    words=tokens(text)
    if not words:return {'relevant':False,'reason':'EMPTY_PROVISION','matched_questions':[]}
    question_hits=[q['id'] for q in question_list if len(words & tokens(q['query']))>=2]
    specific={
       'renewal':{'renovacion','tarjeta','vigencia','larga','duracion','identidad','expedicion'},
       'residence':{'residencia','autorizacion','duracion','temporal','trabajo','arraigo'},
       'nationality':{'nacionalidad','adquisicion','residencia'},
       'arraigo':{'arraigo','excepcionales','residencia'},
       'family':{'reagrupacion','familiar','familiares'},
    }.get(group,set())
    matched=words & specific
    if group=='renewal' and not (words & {'renovacion','vigencia','expedicion','renovar'} or {'tarjeta','identidad'} <= words):
        return {'relevant':False,'reason':'NO_RENEWAL_OR_CARD_PROCEDURE','matched_questions':question_hits}
    if group=='residence' and not (words & {'temporal','duracion','autorizacion','excepcionales','reagrupacion'}):
        return {'relevant':False,'reason':'NO_RESIDENCE_AUTHORIZATION_SUBJECT','matched_questions':question_hits}
    # Border procedures are not adequate evidence of residence categories or renewal.
    if group in ('residence','renewal') and not matched:
        return {'relevant':False,'reason':'UNRELATED_LEGAL_SUBJECT','matched_questions':question_hits}
    if not matched or not question_hits:
        return {'relevant':False,'reason':'NO_RESEARCH_QUESTION_LINK','matched_questions':question_hits}
    return {'relevant':True,'reason':'LEXICAL_CANDIDATE_REQUIRES_SEMANTIC_REVIEW',
            'matched_questions':question_hits,'subject_matches':sorted(matched)}

def _topic_priority_articles(group, topic):
    """Known research entry points, NOT claims that a provision applies.

    These must still pass full-text relevance and independent legal review.
    """
    normalized = normalize(topic)
    if group == 'renewal' and ('permanente' in normalized or 'larga duracion' in normalized):
        return ('185', '209')
    return ()


def _stratified_full_text_probes(rows, limit=48, priority_articles=()):
    """Bounded, reproducible fallback when BOE only labels headings Artículo N.

    This deliberately *does not* treat sampled articles as relevant evidence.
    Every sampled article must pass full-text checks after official retrieval.
    The diagnostic must disclose that some provisions were not inspected.
    """
    if limit <= 0 or not rows:
        return []
    if len(rows) <= limit:
        return list(rows)
    # Protect a small number of known topic-research entry points from being
    # skipped by generic-heading sampling. Match only IDs present in the
    # actual official index, so no article or block ID is invented.
    priority = []
    for number in priority_articles:
        match = next((row for row in rows if row[0] == number), None)
        if match is not None and match not in priority:
            priority.append(match)
    remaining = limit - len(priority)
    if remaining <= 0:
        return priority[:limit]
    # Sample the remainder across the full legislation, not just its start.
    pool = [row for row in rows if row not in priority]
    if remaining == 1:
        positions = [len(pool)//2]
    else:
        positions = sorted({round(i*(len(pool)-1)/(remaining-1)) for i in range(remaining)})
    return sorted(priority + [pool[i] for i in positions],
                  key=lambda row: rows.index(row))


def discover(group,topic,*,index_fetch=api_get,max_per_source=12,full_text_probe_limit=48):
    """Parse actual BOE indexes and rank by subject, not article ordinal position."""
    found=[];diagnostics=[]
    qs=questions(group)
    for doc in SOURCE_CANDIDATES.get(group,[]):
        endpoint=BASE+doc+'/texto/indice'
        report={'document':doc,'index_url':endpoint,'index_nodes':0,'index_articles':0,
                'qualified_candidates':0,'candidates_selected':0,'failure_code':None,
                'discovery_mode':'INDEX_HEADING_RANKING','full_text_probe_count':0,
                'uninspected_index_articles':0,
                'sample_index_headings':[],'rejected_sample':[]}
        try:
            root,_=index_fetch(endpoint)
            items=list(_index_items(root))
            report['index_nodes']=len(items)
            rows=contextual_index(root)
            report['index_articles']=len(rows)
            report['sample_index_headings']=[title[:120] for _,_,title,_ in rows[:5]]
            if not rows:
                report['failure_code']='BOE_INDEX_PARSING_FAILURE'
                diagnostics.append(report);continue
            candidates=[]
            for number,bid,title,context in rows:
                value,scores,hints=_candidate_score(group,topic,title,context,qs)
                if value>0:
                    candidates.append({'source_id':doc,'article':number,'block_id':bid,
                        'title':title,'section_context':context,'score':value,
                        'question_scores':scores,'concept_scores':hints})
                elif len(report['rejected_sample'])<8:
                    report['rejected_sample'].append({'article':number,'heading':title[:120],
                        'reason':'NO_LEXICAL_OR_CONCEPT_MATCH'})
            candidates.sort(key=lambda x:(-x['score'],int(re.match(r'\d+',x['article']).group(0))))
            report['qualified_candidates']=len(candidates)
            report['candidates_selected']=min(max_per_source,len(candidates))
            if not candidates and len(rows) >= 12 and full_text_probe_limit > 0:
                # A parsed index consisting solely of generic 'Artículo N'
                # headings provides no meaningful lexical candidates. Fetch
                # a bounded, document-wide sample for *full-text* filtering.
                # Do not claim exhaustive discovery or automatic sufficiency.
                probes=_stratified_full_text_probes(rows,full_text_probe_limit,
                    _topic_priority_articles(group,topic))
                candidates=[{'source_id':doc,'article':num,'block_id':bid,
                     'title':title,'section_context':context,'score':0.0,
                     'question_scores':{},'concept_scores':{},
                     'discovery_method':'STRATIFIED_FULL_TEXT_PROBE'}
                     for num,bid,title,context in probes]
                report['discovery_mode']='BOUNDED_FULL_TEXT_PROBE'
                report['full_text_probe_count']=len(probes)
                report['uninspected_index_articles']=max(0,len(rows)-len(probes))
                report['failure_code']='INDEX_HEADINGS_UNINFORMATIVE'
                report['candidates_selected']=len(candidates)
            elif not candidates:
                report['failure_code']='NO_RELEVANT_CANDIDATES'
            found.extend(candidates if report['discovery_mode']=='BOUNDED_FULL_TEXT_PROBE' else candidates[:max_per_source]);diagnostics.append(report)
        except Exception as e:
            report['failure_code']='BOE_INDEX_ERROR'
            report['error']=type(e).__name__
            report['detail']=str(e)[:300]
            diagnostics.append(report)
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
