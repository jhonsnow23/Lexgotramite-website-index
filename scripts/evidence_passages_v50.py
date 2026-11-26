"""Literal spans of the stored official extraction, never model-written quotes.
Offsets refer to evidence.text (not the original PDF bytes). Extraction markers
are boundaries, not legal text. The full source remains available for context.
"""
import hashlib
import re
try:
    from official_sources_v50 import allowed
except ImportError:
    from scripts.official_sources_v50 import allowed


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def build_catalog(evidence):
    rows, warnings = {}, []
    counts = {}
    for record in evidence:
        eid = record.get('evidence_id')
        counts[eid] = counts.get(eid, 0) + 1
    for record in evidence:
        eid, text = record.get('evidence_id'), record.get('text')
        if not isinstance(eid, str) or counts[eid] != 1 or not isinstance(text, str) or not allowed(record.get('official_url') or ''):
            warnings.append({'evidence_id': eid, 'reason': 'INVALID_OR_DUPLICATE_SOURCE'})
            continue
        # Do not concatenate excerpts separated by a retrieval omission marker.
        starts = [0]; ends = []
        for match in re.finditer(r'\n\s*\[\.\.\.\]\s*\n', text):
            ends.append(match.start()); starts.append(match.end())
        ends.append(len(text))
        for lo, hi in zip(starts, ends):
            while lo < hi and text[lo].isspace(): lo += 1
            while hi > lo and text[hi-1].isspace(): hi -= 1
            if hi-lo < 20: continue
            # Full contiguous provision/excerpt first, then numbered paragraphs.
            boundaries = [lo] + [lo+m.start() for m in re.finditer(r'(?m)^\d{1,3}\s*\.\s+', text[lo:hi]) if m.start()] + [hi]
            spans = [(lo, hi)] + list(zip(boundaries, boundaries[1:]))
            parent = None
            for a,b in dict.fromkeys(spans):
                while b>a and text[b-1].isspace(): b-=1
                if b-a<20: continue
                quote=text[a:b]; h=digest(quote)
                pid='P_'+digest(f'{eid}|{digest(text)}|{a}|{b}')[:32]
                rows[pid]={'passage_id':pid,'evidence_id':eid,'source_url':record['official_url'],
                    'source_title':record.get('document_title'),'source_type':record.get('authority'),
                    'document_reference':record.get('source_id'),'article_reference':record.get('article'),
                    'section_reference':None,'page_number':None,'verbatim_text':quote,
                    'start_offset':a,'end_offset':b,'text_hash':h,'source_text_hash':digest(text),
                    'retrieved_at':record.get('retrieved_at'),'parent_passage_id':parent}
                if parent is None: parent=pid
    return {'passages':rows,'warnings':warnings,'offset_basis':'stored official evidence.text, not original file bytes'}


def resolve_passage(pid, catalog, evidence, *, allowed_ids=None):
    if not isinstance(pid,str) or pid not in catalog['passages']: return None
    if allowed_ids is not None and pid not in allowed_ids: return None
    p=catalog['passages'][pid]
    matches=[r for r in evidence if r.get('evidence_id')==p['evidence_id']]
    if len(matches)!=1: return None
    r=matches[0]; text=r.get('text',''); a,b=p['start_offset'],p['end_offset']
    if not allowed(r.get('official_url') or '') or r['official_url']!=p['source_url']: return None
    if not (type(a) is int and type(b) is int and 0<=a<b<=len(text)): return None
    if digest(text)!=p['source_text_hash'] or digest(text[a:b])!=p['text_hash'] or text[a:b]!=p['verbatim_text']: return None
    if pid!='P_'+digest(f"{r['evidence_id']}|{digest(text)}|{a}|{b}")[:32]: return None
    return {'passage_id':pid,'evidence_id':r['evidence_id'],'quote':text[a:b]}


def select_context(catalog, evidence, dossier, limit=120000):
    """Use existing focused evidence and applicability, with whole parents first.
    Omit rather than silently truncate; callers fail closed on budget overflow.
    """
    roles={r['evidence_id']:r for r in (dossier or {}).get('applicability_evidence',[])}
    selected=[]; size=0; omitted=[]
    for p in sorted(catalog['passages'].values(), key=lambda p: bool(p['parent_passage_id'])):
        role=roles.get(p['evidence_id'],{})
        if role.get('applicability') not in ('DIRECTLY_APPLICABLE','CONDITIONALLY_APPLICABLE','PROCEDURAL_GUIDANCE'):
            continue
        compact={k:p[k] for k in ('passage_id','evidence_id','verbatim_text','parent_passage_id','article_reference','source_title','document_reference')}
        compact['applicability']=role.get('applicability'); compact['route_ids']=role.get('destination_authorization',[])
        cost=len(p['verbatim_text'])+400
        if size+cost>limit:
            omitted.append(p['passage_id']); continue
        selected.append(compact); size+=cost
    return selected,omitted


def short_passage_context(selected):
    """Per-call aliases; canonical hashes never leave the selection boundary."""
    aliases = {f'P{i:03d}': p['passage_id'] for i, p in enumerate(selected, 1)}
    reverse = {v:k for k,v in aliases.items()}
    rows = [{k:v for k,v in p.items() if k not in ('evidence_id','passage_id','parent_passage_id')} |
            {'passage_id': alias, 'parent_passage_id': reverse.get(p['parent_passage_id'])}
            for alias,p in zip(aliases,selected)]
    return aliases, rows
