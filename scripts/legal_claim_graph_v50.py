#!/usr/bin/env python3
"""Traceable source passage graph. Provenance verification is NOT legal approval."""
from __future__ import annotations
from hashlib import sha256
import re

RD316 = 'BOE-A-2026-8284'
# Operative text signatures confirmed from the RD 316/2026 BOE publication.
PROVISIONS = (
    ('DA20.10', 'Disposición adicional vigésima, apartado 10',
     r'(?<!\d)10\.\s+La autorizaci[oó]n concedida tendr[aá] una vigencia'),
    ('DA21.10', 'Disposición adicional vigesimoprimera, apartado 10',
     r'(?<!\d)10\.\s+La autorizaci[oó]n de residencia temporal por circunstancias excepcionales por raz[oó]n de arraigo extraordinario'),
)


def split_rd316_evidence(evidence):
    """Split *verified signatures* of separate BOE operative passages.

    Fails closed if both anchors aren't present exactly once or order changes.
    Original full-document hash/ID remains available via parent_evidence_id.
    """
    out=[]
    for row in evidence:
        text=row.get('text') or ''
        if row.get('source_id') != 'boe' or RD316 not in (row.get('official_url') or ''):
            out.append(row);continue
        hits=[]
        for ref,label,pattern in PROVISIONS:
            match=list(re.finditer(pattern,text,flags=re.I))
            if len(match)!=1:break
            hits.append((ref,label,match[0].start()))
        if len(hits)!=2 or hits[0][2]>=hits[1][2]:
            out.append({**row,'provision_identification':'UNIDENTIFIED_PROVISION'});continue
        for i,(ref,label,start) in enumerate(hits):
            end=hits[i+1][2] if i+1<len(hits) else len(text)
            segment=text[start:end].strip()
            if segment.endswith('[...]'):
                segment=segment[:-5].rstrip()
            if not segment or 'artículo 191' not in segment.lower():
                out.append({**row,'provision_identification':'UNIDENTIFIED_PROVISION'})
                break
            digest=sha256((row['evidence_id']+'|'+ref+'|'+segment).encode()).hexdigest()
            child={**row,'evidence_id':'EV_'+digest[:20].upper(),'source_id':RD316,
                   'article':ref,'provision':label,'parent_evidence_id':row['evidence_id'],
                   'document_title':row.get('document_title','')+' — '+label,
                   'text':segment,'passage_sha256':sha256(segment.encode()).hexdigest(),
                   'provision_identification':'MATCHED_OPERATIVE_SIGNATURE',
                   'publication_date':'2026-04-15',
                   'legal_reference':{'document':RD316,'provision':label,'paragraph':10},
                   'version_status':'BOE_PUBLICATION_DATE_NOT_CURRENT_CONSOLIDATION'}
            out.append(child)
        else:
            continue
        # A failed split must never create partial or misleading children.
        out=[r for r in out if r.get('parent_evidence_id')!=row['evidence_id']]
        if not any(r['evidence_id']==row['evidence_id'] for r in out):
            out.append({**row,'provision_identification':'UNIDENTIFIED_PROVISION'})
    return out


def _sentences(text):
    # Source-exact anchored excerpts, not synthetic legal paraphrases.
    # Avoid mid-sentence matches produced by the former 450-character regex cap.
    candidates = re.split(r'(?<=[.!?])\s+', text or '')
    return [s.strip() for s in candidates if 40 <= len(s.strip()) <= 1600
            and (s.strip()[0].isupper() or s.strip()[0].isdigit())
            and s.strip()[-1] in '.!?']


def _passage_routes(passage, proposed):
    """Descriptive classification only, never an eligibility decision."""
    low = passage.casefold()
    if 'excepcionalmente' in low and ('prorrog' in low or 'prórrog' in low):
        return [r for r in proposed if r == 'PRORROGA_EXCEPCIONAL']
    if 'prorrogará la validez' in low or 'prorrogara la validez' in low:
        return [r for r in proposed if r == 'MODIFICACION_ART_191']
    if 'modificaci' in low and 'prórroga excepcional' not in low:
        return [r for r in proposed if r == 'MODIFICACION_ART_191']
    return proposed if len(proposed) == 1 else []


def build_source_claims(evidence, dossier, questions):
    """Build claims from exact SOURCE PASSAGES and bidirectional links.

    Citation/question association is model-proposed; literal exactness is verified.
    No legal semantic support is certified merely by presence of a citation.
    """
    byid={row['evidence_id']:row for row in evidence}
    roles={r['evidence_id']:r for r in dossier['applicability_evidence']}
    claim_rows=[]; links=[]
    used=set()
    for q in questions:
        for eid in q.get('evidence_ids') or []:
            row=byid.get(eid); role=roles.get(eid)
            if not row or not role: continue
            if role['applicability'] in ('CONTEXT_ONLY','UNRELATED','UNDETERMINED'):
                continue
            # Select source-exact snippets relevant to the research question;
            # these document excerpts, NOT independently verified conclusions.
            qid=q['id']
            needles={'scope':('modificaci','prórroga','prorrog'),
                     'requirements':('requisitos','acredita','inscri','modificaci'),
                     'steps':('solicitud','presenta','plazo','procedimiento')}.get(qid,())
            match=next((s for s in _sentences(row.get('text'))
                        if any(n in s.lower() for n in needles)),None)
            if not match or match not in row.get('text',''):continue
            key=(qid,eid,match)
            if key in used:continue
            used.add(key)
            cid='CL_'+sha256(('|'.join(key)).encode()).hexdigest()[:20].upper()
            claim_rows.append({'claim_id':cid,'claim_text':match,'claim_kind':'EXACT_SOURCE_EXCERPT',
                'question_id':qid,'evidence_ids':[eid],
                'procedure_routes':_passage_routes(match, role['destination_authorization']),
                'verification_status':'TEXTUAL_PROVENANCE_VERIFIED_LEGAL_APPLICABILITY_PENDING',
                'support_type':'UNVERIFIED','applicability_conditions':role['applicability_conditions'],
                'source_passage':{'evidence_id':eid,'exact_text':match,
                    'sha256':sha256(match.encode()).hexdigest(),
                    'provision':row.get('provision') or row.get('article')},
                'limitations':['Source-exact excerpt does not establish that the quoted rule applies to every case']})
            links.append({'claim_id':cid,'evidence_id':eid,'question_id':qid,
                          'textual_match_verified':True,'legal_support_verified':False})
            role['supported_claims'].append(cid)
    for annotation in dossier['applicability_evidence']:
        if annotation['supported_claims']:
            annotation['verification_status']='TEXTUAL_PROVENANCE_VERIFIED_APPLICABILITY_PENDING'
    return {'schema_version':'1.1','source_claims':claim_rows,'links':links,
            'semantic_legal_support_verified':False,'publication_allowed':False}


def validate_graph(graph,dossier,evidence):
    byid={r['evidence_id']:r for r in evidence}
    annotations={r['evidence_id']:r for r in dossier['applicability_evidence']}
    claim_by_id={r['claim_id']:r for r in graph['source_claims']}
    errors=[]
    for c in graph['source_claims']:
        passage=c['source_passage']; eid=passage['evidence_id']
        if eid not in byid or passage['exact_text'] not in byid[eid].get('text',''):
            errors.append('UNSUPPORTED_PASSAGE:'+c['claim_id'])
        if c['claim_id'] not in annotations.get(eid,{}).get('supported_claims',[]):
            errors.append('MISSING_REVERSE_LINK:'+c['claim_id'])
    for eid,a in annotations.items():
        for cid in a['supported_claims']:
            if cid not in claim_by_id or eid not in claim_by_id[cid]['evidence_ids']:
                errors.append('ORPHAN_REFERENCE:'+eid+':'+cid)
    return errors


def operative_mechanisms(evidence):
    """Locate *distinct* legal effects within each BOE paragraph 10.

    This is provenance extraction, not individual eligibility evaluation.
    """
    results=[]
    for row in evidence:
        if row.get('source_id')!=RD316 or row.get('article') not in ('DA20.10','DA21.10'):
            continue
        body=row.get('text','')
        for kind,phrase in (
            ('EXTENSION_PENDING_MODIFICATION','La presentación de la solicitud prorrogará la validez'),
            ('EXCEPTIONAL_EXTENSION_OF_AUTHORIZATION','Excepcionalmente, si no se pudiera solicitar una modificación')
        ):
            offset=body.find(phrase)
            if offset<0:continue
            start=body.rfind('.',0,offset)+1
            end=body.find('.',offset)
            if end<0:continue
            passage=body[start:end+1].strip()
            if not passage or passage not in body:continue
            results.append({'mechanism_id':row['article']+':'+kind,
                'mechanism_type':kind,'source_evidence_id':row['evidence_id'],
                'provision':row.get('provision'),'exact_source_passage':passage,
                'textual_provenance_verified':True,'legal_applicability_verified':False})
    return results
