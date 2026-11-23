#!/usr/bin/env python3
"""Lex Go Trámite v4.6: evidence-ID based, read-only legal-content candidate.

This is an integration replacement for the v4.1 generation step, NOT a legal
certification or a production publisher. Fail closed on uncertainty.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

try:
    from legal_relevance_v50 import group_of, questions, discover, coverage, metadata_duplicate, provision_relevance
except ImportError:
    from scripts.legal_relevance_v50 import group_of, questions, discover, coverage, metadata_duplicate, provision_relevance

try:
    from official_sources_v50 import retrieve_for_topic as retrieve_official
except ImportError:
    from scripts.official_sources_v50 import retrieve_for_topic as retrieve_official

try:
    from boe_universal_v45 import retrieve, BOEError
except ImportError:
    from scripts.boe_universal_v45 import retrieve, BOEError

# Identified research starting points, not an assertion of legal applicability.
# Do not guess special immigration articles for broadly defined authorizations.
REGISTRY = {
    'nationality': [('BOE-A-1889-4763', ['21', '22', '23']),
                    ('BOE-A-2015-12047', ['1', '2', '3'])],
    'nationality_requirements': [('BOE-A-1889-4763', ['21', '22', '23']),
                                 ('BOE-A-2015-12047', ['1', '2', '3'])],
    'nationality_documents': [('BOE-A-1889-4763', ['21', '22', '23']),
                              ('BOE-A-2015-12047', ['1', '2', '3'])],
    'residency_options': [('BOE-A-2024-24099', ['1', '2'])],
    'legal_residence': [('BOE-A-2024-24099', ['1', '2'])],
    # Authorization-specific research needed; cannot safely conflate regimes.
}
BLUEPRINTS = {
    'nationality': ['Requisitos y plazos según el supuesto','Documentación y acreditación',
                    'Procedimiento y presentación','Excepciones y errores frecuentes'],
    'residence': ['Clases de autorización y alcance','Requisitos por procedimiento',
                  'Documentos y presentación','Limitaciones y situaciones especiales'],
    'renewal': ['Autorización que se pretende renovar','Requisitos y plazos aplicables',
                'Documentación y presentación','Resolución y situaciones especiales'],
    'other': ['A quién se dirige','Requisitos y excepciones',
              'Procedimiento y documentación','Dudas habituales'],
}
SYSTEM_WRITER = '''Eres redactor de información jurídica general española. Usa EXCLUSIVAMENTE la evidencia suministrada.
Los códigos evidence_id son referencias, no afirmaciones legales verificadas.
Devuelve exclusivamente JSON: title,meta_description,introduction,sections (lista {heading,paragraphs}),
faqs (lista {question,answer}),claims (lista {claim,evidence_ids}),unresolved_questions (lista de textos).
Cada afirmación jurídica material debe aparecer en claims y citar IDs existentes. No fabriques fuentes, citas,
plazos, requisitos, asesoramiento individualizado ni acreditaciones profesionales. Explica supuestos, excepciones
 y condiciones; si faltan fuentes que resultan esenciales registra preguntas pendientes. Mínimo 3 secciones
sustantivas cuando la evidencia lo permita. No copies literalmente testimonios o normas extensas.
Nunca afirmes que la revisión jurídica ha concluido o que el artículo está publicado.'''
SYSTEM_REVIEW = '''Eres un evaluador crítico y separado del redactor. Comprueba si cada afirmación jurídica
queda plenamente respaldada por los pasajes oficiales incluidos, considerando excepciones, ámbito, fecha y
condiciones. No supongas que una cita coincidente demuestra aplicabilidad. Devuelve SOLO JSON con
assessment (lista de {claim_index, status, reason}), con status estrictamente SUPPORTED,
PARTIALLY_SUPPORTED, CONTRADICTED, INSUFFICIENT_EVIDENCE, NEEDS_INTERPRETATION.
Si no puedes demostrar apoyo completo, NO uses SUPPORTED. Señala lagunas de cobertura en gaps (lista texto).
Tu evaluación no constituye certificación jurídica independiente.'''


def stable_id(p):
    # Stable across runs of identical official text and legal version.
    material='|'.join([p['source_id'],str(p['article']),str(p.get('version_date') or ''),p['text']])
    return 'EV_'+hashlib.sha256(material.encode('utf-8')).hexdigest()[:20].upper()


def records_from_boe(result):
    output=[]
    for item in result['provisions']:
        eid=stable_id(item)
        output.append({'evidence_id':eid,'source_id':item['source_id'],'article':item['article'],
                       'official_url':result['official_url'],'api_url':item['api_url'],
                       'retrieved_at':item['retrieved_at'],'version_date':item.get('version_date'),
                       'version_status':item.get('version_status','VERSION_UNCERTAIN'),
                       'legal_status':item.get('legal_status','UNVERIFIED'),
                       'authority':'boe','document_title':item['source_id'], 'text':item['text'],'sha256':hashlib.sha256(item['text'].encode()).hexdigest()})
    return output


def plan(proposal):
    p=proposal['proposals'][0]
    cid=p.get('origin_cluster_id') or p.get('cluster_id','')
    topic=p.get('proposed_title','').strip()
    if not topic:raise ValueError('Proposal missing topic')
    group=group_of(cid,topic)
    return {'topic':topic,'cluster_id':cid,'group':group,
            'queries':p.get('queries',[])[:12],
            'search_demand':p.get('search_demand_evidence',{}),
            'research_questions':questions(group),
            'source_registry_complete':bool(questions(group)),
            'existing_page_action':p.get('action'),
            'duplicate_metadata':metadata_duplicate(p),
            'publication_allowed':False}


def retrieve_evidence(research_plan,retrieval=retrieve,*,discovery=discover,return_diagnostics=False,include_official=False,official_retrieval=None):
    """Bounded official candidate retrieval; reject unrelated full text before drafting.

    A retrieval warning does not create legal evidence; the independent research-
    readiness gate still decides whether every essential question has support.
    """
    candidates,diagnostics=discovery(research_plan['group'],research_plan['topic'])
    evidence=[];errors=[];attempts=[];seen=set()
    for c in candidates:
        key=(c['source_id'],c['article'])
        if key in seen:continue
        seen.add(key)
        trial={'document':c['source_id'],'article':c['article'],
               'heading':c.get('title',''), 'index_score':c.get('score',0),
               'index_question_scores':c.get('question_scores',{}),
               'stage':'FULL_TEXT_RETRIEVAL',
               'discovery_method':c.get('discovery_method','INDEX_HEADING_RANKING')}
        try:
            if retrieval is retrieve and c.get('block_id') and str(c.get('article','')).isdigit():
                # Reuse the official index mapping discovered immediately before
                # retrieval: avoids downloading the same ~265-item index 48x.
                response=retrieval(c['source_id'],[c['article']],
                    verified_index_mapping={(int(c['article']),''):c['block_id']})
            else:
                response=retrieval(c['source_id'],[c['article']])
            rows=records_from_boe(response)
            if not rows or str(rows[0]['article'])!=str(c['article']):
                raise ValueError('Requested article identity mismatch')
            for rec in rows:
                guard=provision_relevance(research_plan['group'],research_plan['topic'],
                       rec['text'],research_plan['research_questions'])
                trial['full_text_relevance']=guard
                if not guard['relevant']:
                    trial['stage']='REJECTED_FULL_TEXT';continue
                rec['research_relevance']={'index_heading':c.get('title',''),
                  'question_scores':c.get('question_scores',{}),
                  'subject_matches':guard.get('subject_matches',[]),
                  'semantic_verification_required':True}
                evidence.append(rec);trial['stage']='EVIDENCE_CANDIDATE'
        except Exception as ex:
            trial['stage']='RETRIEVAL_ERROR'
            trial['error_code']=getattr(ex,'code',type(ex).__name__)
            trial['detail']=str(ex)[:250]
            errors.append({'document':c['source_id'],'article':c['article'],
                 'category':trial['error_code'],'details':trial['detail']})
        attempts.append(trial)
    if not candidates:
        codes=[x.get('failure_code') for x in diagnostics if x.get('failure_code')]
        code='BOE_INDEX_PARSING_FAILURE' if 'BOE_INDEX_PARSING_FAILURE' in codes else 'NO_RELEVANT_CANDIDATES'
        errors.append({'category':code,
              'details':'Index could not yield topic-relevant provision candidates; see discovery_diagnostics.json'})
    elif not evidence:
        errors.append({'category':'RELEVANCE_FILTER_REJECTED_ALL',
              'details':'No retrieved provision satisfied the full-text subject guard; see discovery_diagnostics.json. A bounded probe cannot prove no relevant law exists.'})
    for item in diagnostics:
        if item.get('error') or item.get('failure_code')=='BOE_INDEX_ERROR':
            errors.append({'category':item.get('failure_code','BOE_INDEX_ERROR'),
                           'details':item.get('detail','BOE index request failed'),
                           'document':item.get('document')})
    official_attempts=[]
    if include_official:
        extra,extra_errors,official_attempts=(official_retrieval or retrieve_official)(research_plan['topic'], research_plan['group'])
        evidence.extend(extra)
        errors.extend(extra_errors)
    if return_diagnostics:return evidence,errors,{'official_source_attempts':official_attempts,'index':diagnostics,'provision_attempts':attempts,
                 'retrieved_candidates':len(attempts),'accepted_evidence':len(evidence),
                 'full_text_probes_attempted':sum(t.get('discovery_method')=='STRATIFIED_FULL_TEXT_PROBE' for t in attempts),
                 'discovery_exhaustive':all(not r.get('uninspected_index_articles') for r in diagnostics)}
    return evidence,errors

def call_model(messages,*,model='gpt-4.1-mini',client=None):
    key=os.environ.get('OPENAI_API_KEY')
    if not key and client is None:raise RuntimeError('OPENAI_API_KEY missing')
    payload={'model':model,'response_format':{'type':'json_object'},'temperature':0.1,
             'messages':messages}
    if client:
        result=client(payload)
    else:
        req=urllib.request.Request('https://api.openai.com/v1/chat/completions',
            data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),method='POST',
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=100) as response:result=json.load(response)
    content=result['choices'][0]['message']['content']
    return json.loads(content) if isinstance(content,str) else content


def article_request(research_plan,evidence,model='gpt-4.1-mini',client=None,previous=None,findings=None):
    data={'plan':research_plan,'evidence':evidence,'previous_draft':previous,
          'problems_to_correct':findings,'instructions':'Cite evidence_id only; never invent sources.'}
    messages=[{'role':'system','content':SYSTEM_WRITER},
              {'role':'user','content':json.dumps(data,ensure_ascii=False)}]
    return call_model(messages,model=model,client=client)


def verify_integrity(article,evidence,plan_obj):
    errors=[];ids={r['evidence_id']:r for r in evidence};claims=article.get('claims')
    if not isinstance(claims,list) or not claims:errors.append('No legal claims')
    else:
        for i,c in enumerate(claims):
            if not isinstance(c,dict) or len(str(c.get('claim','')).strip())<12:
                errors.append(f'Claim {i+1} missing text');continue
            refs=c.get('evidence_ids')
            if not isinstance(refs,list) or not refs:
                errors.append(f'Claim {i+1} lacks evidence IDs');continue
            if any(x not in ids for x in refs):errors.append(f'Claim {i+1} cites unknown evidence ID')
    sections=article.get('sections')
    if not isinstance(sections,list) or len(sections)<3:errors.append('Insufficient substantive sections')
    else:
        for i,sec in enumerate(sections):
            if not isinstance(sec,dict) or not isinstance(sec.get('heading'),str) or not isinstance(sec.get('paragraphs'),list) or not any(isinstance(p,str) and len(p)>55 for p in sec['paragraphs']):
                errors.append(f'Section {i+1} is incomplete')
    for k in ('title','meta_description','introduction'):
        if not isinstance(article.get(k),str) or len(article[k].strip())<35:errors.append(f'Incomplete {k}')
    if not isinstance(article.get('unresolved_questions'),list):errors.append('Missing unresolved question list')
    elif article['unresolved_questions']:errors.append('Unresolved legal questions')
    blob=json.dumps(article,ensure_ascii=False)
    if re.search(r'\[PENDIENTE\]|TODO:|lorem ipsum',blob,re.I):errors.append('Placeholder detected')
    if any(x.get('version_status')=='VERSION_UNCERTAIN' for x in evidence):
        errors.append('One or more provisions have uncertain version dates')
    if not plan_obj['source_registry_complete']:errors.append('Legal source scope not established')
    if plan_obj.get('existing_page_action')=='improve_existing_page':
        errors.append('Existing article has not been reconciled; replacement forbidden')
    return errors


def semantic_review(article,evidence,model='gpt-4.1-mini',client=None):
    claims=article.get('claims',[])
    ids={r['evidence_id']:r for r in evidence}
    annotated=[]
    for i,c in enumerate(claims):
        annotated.append({'claim_index':i,'claim':c.get('claim',''),
            'evidence':[ids[x] for x in c.get('evidence_ids',[]) if x in ids]})
    resp=call_model([{'role':'system','content':SYSTEM_REVIEW},
                     {'role':'user','content':json.dumps({'claims':annotated,'article':article},ensure_ascii=False)}],model=model,client=client)
    assessments=resp.get('assessment',[])
    problems=[]
    if not isinstance(assessments,list) or len(assessments)!=len(claims):
        problems.append('Reviewer did not evaluate all claims')
    else:
        seen=set()
        for entry in assessments:
            idx=entry.get('claim_index')
            if not isinstance(idx,int) or idx in seen or not (0<=idx<len(claims)):
                problems.append('Reviewer returned invalid claim index');continue
            seen.add(idx)
            if entry.get('status')!='SUPPORTED':
                problems.append(f'Claim {idx+1}: {entry.get("status","UNKNOWN")}')
        if len(seen)!=len(claims):problems.append('Reviewer omitted claim indices')
    if resp.get('gaps'):problems.append('Reviewer identified coverage gaps')
    return resp,problems


def render(article,evidence,validation):
    esc=lambda v:escape(str(v),quote=True)
    title=esc(article.get('title','BORRADOR'))
    sections=''.join('<section><h2>'+esc(x.get('heading',''))+'</h2>'+''.join('<p>'+esc(p)+'</p>' for p in x.get('paragraphs',[]))+'</section>' for x in article.get('sections',[]) if isinstance(x,dict))
    faqs=''.join('<h3>'+esc(q.get('question',''))+'</h3><p>'+esc(q.get('answer',''))+'</p>' for q in article.get('faqs',[]) if isinstance(q,dict))
    # Evidence lookup owned by Python, not model-generated citations.
    trace=''.join('<li>'+esc(c.get('claim',''))+' — '+', '.join(esc(ref) for ref in c.get('evidence_ids',[]))+'</li>' for c in article.get('claims',[]) if isinstance(c,dict))
    refs=''.join('<li>'+esc(r.get('document_title') or r['source_id'])+((', artículo '+esc(r['article'])) if r.get('article') else '')+' — <a href="'+esc(r['official_url'])+'">Fuente oficial</a> (consultado '+esc(r['retrieved_at'][:10])+')</li>' for r in evidence)
    return '<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BORRADOR — '+title+'</title><meta name="description" content="'+esc(article.get('meta_description',''))+'"></head><body><main><strong>BORRADOR — NO PUBLICAR. Verificación jurídica independiente pendiente.</strong><h1>'+title+'</h1><p>'+esc(article.get('introduction',''))+'</p>'+sections+'<section><h2>Preguntas frecuentes</h2>'+faqs+'</section><section><h2>Trazabilidad de afirmaciones (revisión pendiente)</h2><ul>'+trace+'</ul></section><section><h2>Fuentes oficiales y normativa consultada</h2><ul>'+refs+'</ul></section><p>Información general, sujeta a revisión y a las circunstancias individuales.</p></main></body></html>'


def research_readiness(research_plan,evidence,*,model='gpt-4.1-mini',client=None):
    if not evidence:return coverage(research_plan['research_questions'],evidence)
    prompt=('Review each question strictly against supplied official evidence. '
       'Return JSON object with `questions` array of objects id,status,evidence_ids,reason. '
       'Only ANSWERED_WITH_EVIDENCE if evidence fully answers the question with exceptions; '
       'otherwise use PARTIALLY_ANSWERED, NOT_ANSWERED, or REQUIRES_LEGAL_INTERPRETATION. '
       'Never invent an evidence_id. This is a research-readiness assessment, not a legal certification.')
    result=call_model([{'role':'system','content':prompt},
       {'role':'user','content':json.dumps({'topic':research_plan['topic'],
           'questions':research_plan['research_questions'],'evidence':evidence},ensure_ascii=False)}],
       model=model,client=client)
    judgments={q['id']:q for q in result.get('questions',[]) if isinstance(q,dict) and q.get('id')}
    return coverage(research_plan['research_questions'],evidence,semantic_judgments=judgments)


def execute(proposals_path,output_path,*,model='gpt-4.1-mini',retrieval=retrieve,client=None,max_revisions=2):
    out=Path(output_path);out.mkdir(parents=True,exist_ok=True)
    status={'version':'5.0','publication_allowed':False,'result':'BLOCKED','errors':[],
            'independent_legal_accuracy_verified':False,'live_release_enabled':False}
    def save(name,obj):
        (out/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')
    try:
        proposal=json.loads(Path(proposals_path).read_text(encoding='utf-8'))
        research_plan=plan(proposal);save('research_plan.json',research_plan)
        if research_plan['duplicate_metadata']:
            status['result']='SKIPPED_DUPLICATE_TOPIC'
            status['errors']=['Existing title/URL overlaps this topic; blog bodies were not accessed']
            return 0
        if not research_plan['source_registry_complete']:
            status['result']='BLOCKED_INSUFFICIENT_EVIDENCE'
            status['errors']=['No applicable research template for this topic']
            return 2
        evidence,failed,discovery_diagnostics=retrieve_evidence(research_plan,retrieval=retrieval,return_diagnostics=True,include_official=(retrieval is retrieve))
        save('evidence.json',evidence);save('retrieval_errors.json',failed)
        save('discovery_diagnostics.json',discovery_diagnostics)
        if failed or not evidence:
            status['errors']=['Evidence retrieval incomplete']+[x.get('details',x.get('detail','')) for x in failed]
            status['result']='BLOCKED_INSUFFICIENT_EVIDENCE'
            status['failure_codes']=[x.get('category') for x in failed]
            return 2
        covered,ready=research_readiness(research_plan,evidence,model=model,client=client)
        save('research_coverage.json',{'questions':covered,'ready':ready,
             'publication_allowed':False})
        if not ready:
            status['result']='BLOCKED_IRRELEVANT_OR_INCOMPLETE_EVIDENCE'
            status['errors']=['Official provisions do not answer every essential research question']
            return 2
        audit=[];draft=None
        for attempt in range(max_revisions+1):
            previous=draft
            draft=article_request(research_plan,evidence,model=model,client=client,previous=previous,
                    findings=audit[-1] if audit else None)
            integrity=verify_integrity(draft,evidence,research_plan)
            review,review_errors=semantic_review(draft,evidence,model=model,client=client) if not any('unknown evidence ID' in x for x in integrity) else ({'assessment':[]},['Invalid citations'])
            issues=integrity+review_errors
            audit.append({'attempt':attempt+1,'integrity_errors':integrity,'review':review,'blocking_errors':issues})
            if not issues:break
        save('article.json',draft);save('verification.json',audit)
        (out/'article.preview.html').write_text(render(draft,evidence,audit[-1]),encoding='utf-8')
        status['result']='REVIEW_READY' if not audit[-1]['blocking_errors'] else 'BLOCKED_VALIDATION'
        status['errors']=audit[-1]['blocking_errors']
        status['attempts']=len(audit)
        # Even an unflagged automated pass cannot certify immigration-law correctness.
        return 0 if status['result']=='REVIEW_READY' else 3
    except Exception as exc:
        status['errors']=[type(exc).__name__+': '+str(exc)[:250]]
        status['result']='ERROR'
        return 4
    finally:
        save('decision.json',status)
        print(json.dumps({'result':status['result'],'publication_allowed':False,'errors':status['errors']},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--proposals',default='reports/seo_v42/selected_v41_proposal.json')
    parser.add_argument('--output',default='reports/seo_v46')
    parser.add_argument('--model',default='gpt-4.1-mini')
    args=parser.parse_args()
    return execute(args.proposals,args.output,model=args.model)

if __name__=='__main__':sys.exit(main())
