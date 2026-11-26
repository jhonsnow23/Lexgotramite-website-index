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
    from temporary_residence_policy_v50 import classify as classify_temporary, research_questions as temporary_questions
except ImportError:
    from scripts.temporary_residence_policy_v50 import classify as classify_temporary, research_questions as temporary_questions

try:
    from official_sources_v50 import retrieve_for_topic as retrieve_official
except ImportError:
    from scripts.official_sources_v50 import retrieve_for_topic as retrieve_official

try:
    from legal_applicability_v50 import (build_dossier, question_matrix, scope_conflicts, audit_declared_claims, general_guidance_branch_coverage)
except ImportError:
    from scripts.legal_applicability_v50 import (build_dossier, question_matrix, scope_conflicts, audit_declared_claims, general_guidance_branch_coverage)

try:
    from legal_claim_graph_v50 import split_rd316_evidence, build_source_claims, validate_graph, operative_mechanisms
except ImportError:
    from scripts.legal_claim_graph_v50 import split_rd316_evidence, build_source_claims, validate_graph, operative_mechanisms

try:
    from boe_universal_v45 import retrieve, BOEError
except ImportError:
    from scripts.boe_universal_v45 import retrieve, BOEError

try:
    from evidence_passages_v50 import build_catalog, resolve_passage, select_context, short_passage_context
except ImportError:
    from scripts.evidence_passages_v50 import build_catalog, resolve_passage, select_context, short_passage_context

try:
    from editorial_scope_v50 import alternative_scope
except ImportError:
    from scripts.editorial_scope_v50 import alternative_scope

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
SYSTEM_WRITER = '''Eres redactor jurídico especializado en la CONTINUIDAD DE AUTORIZACIONES TEMPORALES
DE RESIDENCIA Y TRABAJO en España. Las únicas seis categorías editoriales permitidas son:
regularización extraordinaria 2026, arraigo, cuenta ajena, cuenta propia, no lucrativa y menores
acompañados no nacidos en España. Nunca redactes sobre renovación de TIE de larga duración,
residencia permanente, cita de huellas o nacionalidad como tema principal.

Primero identifica si el trámite vigente es RENOVACIÓN, MODIFICACIÓN o PRÓRROGA; no infieras
su equivalencia por las palabras del usuario. Para regularización de 2026 comprueba las
disposiciones adicionales vigésima y vigesimoprimera y el artículo 191 cuando procedan.
No generalices un régimen de arraigo a otro, ni traslades requisitos de autorización inicial a
renovación, modificación o prórroga, salvo cuando una remisión normativa expresa los incorpore
a una rama concreta, como el artículo 191.2 respecto del artículo 74. Para una guía GENERAL de continuidad de la
regularización, explica las ramas de decisión y cuándo es necesaria revisión
individual; no prometas un listado completo de requisitos/documentos para
ambas ramas, ni presentes una guía general como instrucciones personalizadas. Distingue las reglas transitorias cuando corresponda.
Para titulares de las autorizaciones de las disposiciones adicionales vigésima y vigesimoprimera:
ambas autorizaciones habilitan a trabajar por cuenta ajena y propia según su apartado 10.
En el artículo 191: (i) el apartado 2 remite al artículo 74 para la modificación por cuenta ajena
cuando todavía no se lleva residiendo al menos un año como titular de una autorización de residencia;
(ii) el apartado 3, si se lleva en España al menos un año en situación de residencia y la autorización de origen habilitaba a trabajar, remite al artículo 80 para cuenta ajena
o al artículo 86 para cuenta propia; (iii) el apartado 4 y su remisión al artículo 84 corresponden
a autorizaciones de origen que NO habilitaban a trabajar y no deben trasladarse automáticamente
a titulares DA20/DA21. No infieras una vía de cuenta propia antes de un año si la norma y la evidencia
suministrada no la establecen expresamente. Distingue la prolongación de validez mientras se resuelve
una modificación de la prórroga excepcional de la autorización. La prórroga excepcional solo se
explicará con las condiciones y duraciones expresamente contenidas en DA20.10/DA21.10.
Escribe español de España útil para potenciales clientes, con CTA natural para Lex Go Trámite,
pero no prometas aprobaciones ni servicios no demostrados.

ATENCIÓN CRÍTICA PARA REGULARIZACIÓN EXTRAORDINARIA 2026: las disposiciones
adicionales que regulan el ACCESO INICIAL a la autorización no son por sí mismas
una vía para renovar esa misma autorización tras su concesión. Si el lector ya
es titular, investiga exclusivamente qué ocurre AL VENCIMIENTO y cuál es el
procedimiento posterior aplicable. No presentes requisitos iniciales (entrada
antes de 2026, permanencia previa, antecedentes para solicitar el arraigo
extraordinario, fecha límite de solicitud inicial) como requisitos de una
modificación o prórroga posterior. Usa la guía ministerial específica de
modificación o prórroga y la norma aplicable. Cuando no exista evidencia
suficiente, declara la duda material y bloquea el borrador.
La lista cerrada de IDs válidos es exactamente la de los registros de evidencia
recibidos: copia IDs completos sin añadirles hashes, prefijos ni sufijos.

Usa SOLO evidencia oficial proporcionada; un registro de fuente recuperada NO certifica su
aplicabilidad jurídica. No inventes tasas, plazos, requisitos ni vías de presentación; no
extraigas conclusiones negativas a partir del silencio de las fuentes. Si el expediente marca
como no verificados un canal exclusivo o una lista completa de documentos, no los afirmes ni
insinúes que no existen; limita el texto a los pasos acreditados y señala que esos detalles
deben confirmarse en el canal oficial vigente antes de presentar la solicitud.
Devuelve exclusivamente JSON con title, meta_description, introduction,
sections (lista {heading,paragraphs}), faqs (lista {question,answer}),
claims (lista {claim,evidence_ids}), unresolved_questions (lista de textos).
Cada afirmación legal material, incluso en FAQ o introducción, debe estar en claims con IDs
válidos de la evidencia. No copies largos textos normativos. Al menos tres secciones sustantivas.
Separa dudas materiales que impiden explicar el trámite de temas hipotéticos fuera de alcance.
Respeta las limitaciones de research_coverage.gap_assessments: conserva el alcance original,
explica las vías acreditadas y expresa las exclusiones editoriales en el texto sin decidirlas.
No conviertas una vía no verificada en imposibilidad de modificación ni en acceso a prórroga excepcional.
Las exclusiones separables no pertenecen a unresolved_questions, que sigue reservado a dudas materiales.
Nunca ocultes una duda material para alcanzar REVIEW_READY. El resultado siempre es BORRADOR
pendiente de revisión jurídica humana; no autorices publicar.'''

SYSTEM_REVIEW = '''Eres un revisor jurídico independiente del generador.
Devuelve JSON: assessment (lista {claim_index,status,reason}), gaps (lista de textos),
editorial_notes (lista opcional). status solo SUPPORTED, PARTIALLY_SUPPORTED,
CONTRADICTED, INSUFFICIENT_EVIDENCE, NEEDS_INTERPRETATION.
Revisa ABSOLUTAMENTE TODO el texto: introducción, secciones, FAQ, título y claims.
Compara con la evidencia oficial suministrada, competencia, fecha y procedimiento aplicable.
Cualquier afirmación legal material sin claim o sin evidencia específica es un gap bloqueante.
Especialmente revisa si un texto sobre el acceso INICIAL a la regularización se está usando falsamente como instrucción para CONTINUAR una autorización ya concedida. Revisa la diferencia entre RENOVACIÓN, MODIFICACIÓN y PRÓRROGA, así como
regímenes transitorios y requisitos de concesión inicial frente a continuidad.
Una fuente recuperada sin vigencia verificada o un enlace de un trámite distinto no certifica
la afirmación. No marques SUPPORTED si faltan excepciones necesarias. Respeta las remisiones normativas expresas: el artículo 74 solo entra en la rama 191.2 de cuenta ajena; los artículos 80 y 86 aportan requisitos a la modificación 191.3, no convierten el trámite en una renovación autónoma. Para titulares DA20/DA21,
comprueba la matriz de ramas del artículo 191: art. 74 solo en la rama 191.2 de cuenta ajena
antes de un año residiendo como titular de una autorización de residencia; art. 80 en 191.3
cuenta ajena con al menos un año en España en situación de residencia y autorización de origen
habilitante; art. 86 en 191.3 cuenta propia bajo esas mismas condiciones; art. 84 pertenece a
191.4 cuando se lleva al menos un año en España en situación de residencia y el origen no habilitaba a trabajar y no debe imponerse a DA20/DA21. Distingue la
prolongación de validez durante una modificación de la prórroga excepcional de la autorización.
Comprueba las limitaciones de research_coverage y el alcance original de la guía.
Si research_coverage contiene exclusiones editoriales o draft_readiness READY_WITH_DECLARED_LIMITATIONS, devuelve además scope_limitations_status: SUPPORTED o BLOCKED. Revisa también las condiciones individuales, los detalles omitidos y las lagunas supuestamente resueltas mediante evidencia; no basta con que el evaluador previo las haya aceptado.
Solo SUPPORTED si todas las exclusiones son separables, explícitas y compatibles con el alcance original.
Una exclusión editorial solo es válida si es separable y se declara expresamente en el texto;
si impide explicar una condición material, contradice el alcance original o se usa para concluir
que una vía no existe o que procede una prórroga excepcional, informa un gap bloqueante.
No inventes preguntas sobre escenarios que el artículo no afirma cubrir.
Gaps se limita a fallos jurídicos materiales; recomendaciones de estilo van en editorial_notes.
No relajes los criterios para alcanzar REVIEW_READY y nunca autorices publicación.'''


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
    classification=classify_temporary(topic,p.get('queries',[]),cid)
    if classification['excluded']:
        raise ValueError('OUT_OF_SCOPE_TOPIC: '+str(classification['exclusion_reason']))
    group='renewal' if classification['business_category'] not in ('arraigo','regularizacion_2026') else 'arraigo'
    research_questions=temporary_questions(classification['business_category'])
    return {'topic':topic,'cluster_id':cid,'group':group,'commercial_classification':classification,
            'legal_regime':('REGULARIZACION_EXTRAORDINARIA_2026' if classification['business_category']=='regularizacion_2026' else classification['business_category'].upper()),
            'discovery_group_legacy':group,
            'queries':p.get('queries',[])[:12],
            'search_demand':p.get('search_demand_evidence',{}),
            'research_questions':research_questions,
            'source_registry_complete':bool(research_questions),
            'existing_page_action':p.get('action'),
            'duplicate_metadata':metadata_duplicate(p),
            'publication_allowed':False}


def retrieve_referenced_modification_requirements(evidence, retrieval=retrieve):
    """Retrieve provisions explicitly referenced by Art. 191 for legal review.

    These provisions are CONTEXT for different modification branches, not proof
    that all of their requirements apply to a particular applicant. An outage
    is diagnostic and does not create fabricated legal evidence.
    """
    references=('74','80','84','86')
    source='BOE-A-2024-24099'
    existing={(str(x.get('source_id')),str(x.get('article'))) for x in evidence}
    added, warnings, attempts=[],[],[]
    for article in references:
        if (source,article) in existing:
            continue
        attempt={'document':source,'article':article,'role':'ARTICLE_191_CROSS_REFERENCE',
                 'status':'NOT_RETRIEVED'}
        try:
            response=retrieval(source,[article])
            rows=records_from_boe(response)
            for row in rows:
                if str(row.get('article'))!=article or row.get('source_id')!=source:
                    continue
                row['research_relevance']={
                    'reason':'EXPLICIT_CROSS_REFERENCE_IN_ARTICLE_191',
                    'semantic_verification_required':True,
                    'context_only':True,
                    'not_automatically_applicable':True,
                }
                added.append(row)
                attempt['status']='RETRIEVED_UNVERIFIED'
                break
            if attempt['status']!='RETRIEVED_UNVERIFIED':
                raise ValueError('Referenced article identity mismatch')
        except Exception as exc:
            attempt['status']='RETRIEVAL_ERROR'
            attempt['error_code']=getattr(exc,'code',type(exc).__name__)
            warnings.append({'category':'OFFICIAL_SOURCE_RETRIEVAL_ERROR',
                'document':source,'article':article,
                'details':'Article 191 cross-reference: '+str(exc)[:180]})
        attempts.append(attempt)
    return added,warnings,attempts


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
    cross_reference_attempts=[]
    category=research_plan.get('commercial_classification',{}).get('business_category')
    has_191=any(x.get('source_id')=='BOE-A-2024-24099' and
                str(x.get('article'))=='191' for x in evidence)
    # Only follow explicit legal cross-references for post-grant regularisation.
    # Do not broaden other categories or allow these clauses to certify readiness.
    if category=='regularizacion_2026' and has_191 and include_official:
        extra,ref_warnings,cross_reference_attempts=retrieve_referenced_modification_requirements(
            evidence,retrieval=retrieval)
        evidence.extend(extra)
        errors.extend(ref_warnings)
    if return_diagnostics:return evidence,errors,{'cross_reference_attempts':cross_reference_attempts,'official_source_attempts':official_attempts,'index':diagnostics,'provision_attempts':attempts,
                 'retrieved_candidates':len(attempts),'accepted_evidence':len(evidence),
                 'full_text_probes_attempted':sum(t.get('discovery_method')=='STRATIFIED_FULL_TEXT_PROBE' for t in attempts),
                 'discovery_exhaustive':all(not r.get('uninspected_index_articles') for r in diagnostics)}
    return evidence,errors

def call_model(messages,*,model='gpt-4.1-mini',client=None,response_format=None,diagnostics=None):
    key=os.environ.get('OPENAI_API_KEY')
    if not key and client is None:raise RuntimeError('OPENAI_API_KEY missing')
    payload={'model':model,'response_format':response_format or {'type':'json_object'},'temperature':0.1,
             'messages':messages}
    if client:
        result=client(payload)
    else:
        req=urllib.request.Request('https://api.openai.com/v1/chat/completions',
            data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),method='POST',
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=100) as response:result=json.load(response)
    choice=result['choices'][0]
    message=choice['message']
    content=message.get('content')
    if diagnostics is not None:
        diagnostics.update({'finish_reason':choice.get('finish_reason'),
                            'raw_response':_safe_raw_response(content),
                            'refusal':bool(message.get('refusal'))})
    if message.get('refusal') or choice.get('finish_reason') in ('length','content_filter'):
        raise ValueError('Incomplete or refused model response')
    return json.loads(content) if isinstance(content,str) else content


def article_request(research_plan,evidence,model='gpt-4.1-mini',client=None,previous=None,findings=None,dossier=None,research_coverage=None):
    data={'plan':research_plan,'evidence':evidence,'previous_draft':previous,
          'problems_to_correct':findings,'legal_applicability_dossier':dossier,
          'research_coverage':research_coverage,'instructions':'Cite exact evidence_id values only from the provided evidence array; never invent sources or append hashes. For regularizacion_2026, distinguish initial extraordinary arraigo application from post-grant modification/prórroga.'}
    if findings and isinstance(previous,dict):
        # Make the correction target concrete. This does not clear or downgrade
        # the unresolved list: the next model output is validated from scratch.
        data['revision_requirements'] = {
            'critical': 'Correct or remove unsupported statements; never invent supporting sources. Repair every unknown evidence ID using ONLY exact IDs present in the current evidence list; do not assign an arbitrary matching ID.',
            'unresolved_questions_to_resolve_or_justify': previous.get('unresolved_questions',[]),
            'rule': 'Do not carry forward optional exploratory questions. Keep only concrete, material unresolved legal issues that prevent safely describing the requested ordinary procedure.',
            'review_gaps': (findings.get('review') or {}).get('gaps',[]),
            'do_not_claim': 'Exclusively presencial, no online option exists, or no additional legal requirements exist, unless exact evidence proves it.',
        }
    if research_plan.get('adaptive_editorial_scope'):
        data['instructions'] += ' Use exactly the authorized title and ONLY the approved answers and limitations in plan.adaptive_editorial_scope. The original broad topic is not the scope. Include the approved reader-facing scope limitations explicitly in the article, including the boundary of the specific route and any unverified procedural details. Never reintroduce excluded gaps or infer legal absence.'
    messages=[{'role':'system','content':SYSTEM_WRITER},
              {'role':'user','content':json.dumps(data,ensure_ascii=False)}]
    return call_model(messages,model=model,client=client)


def renewal_scope_warnings(article, plan_obj):
    """Flag potential initial-authorization versus TIE-renewal conflation.

    This is a conservative review gate, never a legal certification.
    """
    import unicodedata
    def normal(value):
        value=unicodedata.normalize('NFKD',str(value).lower())
        return ''.join(c for c in value if not unicodedata.combining(c))
    topic=normal(plan_obj.get('topic',''))
    if plan_obj.get('group')!='renewal' or not any(x in topic for x in ('permanente','larga duracion')):
        return []
    problems=[]
    for i,section in enumerate(article.get('sections') or []):
        if not isinstance(section,dict):continue
        heading=normal(section.get('heading',''))
        if not any(x in heading for x in ('requisit','document')):continue
        for paragraph in section.get('paragraphs',[]):
            t=normal(paragraph)
            initial_five_years=(('cinco anos' in t or '5 anos' in t) and
               ('residencia legal' in t or 'residencia continuada' in t))
            initial_background=('antecedentes penales' in t and 'renov' in t)
            clearly_separated=any(x in t for x in ('concesion inicial',
                 'obtencion inicial','solicitud inicial','no es un requisito de renovacion',
                 'no se exige para renovar'))
            if (initial_five_years or initial_background) and not clearly_separated:
                problems.append(f'Section {i+1}: potential initial-authorization requirements conflated with TIE renewal')
    # Detect misleading affirmative assertions in any published article text,
    # not only in FAQ answers or claim metadata. This does not certify the law.
    texts=[('Introduction',article.get('introduction',''))]
    texts += [(f'Section {i+1}',p) for i,sec in enumerate(article.get('sections') or [])
              if isinstance(sec,dict) for p in sec.get('paragraphs',[]) if isinstance(p,str)]
    texts += [(f'FAQ {i+1}',faq.get('answer','')) for i,faq in enumerate(article.get('faqs') or [])
              if isinstance(faq,dict)]
    for i,claim in enumerate(article.get('claims') or []):
        if isinstance(claim,dict):texts.append((f'Claim {i+1}',claim.get('claim','')))
    for location,passage in texts:
        t=normal(passage)
        # Avoid matching explicit statements that the authorization is NOT renewed.
        misleading_auth=(re.search(r'autorizacion de residencia(?: de larga duracion(?: nacional)?)?.{0,55}(?:puede renovarse|se renueva mediante|debe renovarse)',t)
                         or re.search(r'renovacion (?:periodica )?de la autorizacion de residencia de larga duracion',t))
        negated=any(x in t for x in ('no se renueva','no necesita renovacion',
               'no implica renovacion','no implica la renovacion','no equivale a renovar','no debe renovarse'))
        if misleading_auth and not negated:
            problems.append(f'{location}: potential renewal claim for indefinite long-term authorization')
        # Absolute channel statements require special evidence; flag for review,
        # rather than silently changing the article or dropping a claim.
        if re.search(r'(?:no consta|no hay|no se ha encontrado).{0,65}(?:evidencia|prueba|informaci[oó]n).{0,65}(?:telem[aá]tic|online|electr[oó]nic)|(?:telem[aá]tic|online).{0,65}(?:no se excluye|no consta)',t):
            problems.append(f'{location}: speculative lack-of-online-evidence claim belongs in research diagnostics, not article')
        if re.search(r'(?:solicitud|renovacion).{0,55}(?:debe presentarse personalmente|obligatoriamente presencial|exclusivamente presencial)',t):
            problems.append(f'{location}: absolute in-person submission statement requires procedure-specific proof')
    # FAQs are published assertions too, not merely supporting copy.
    for i, faq in enumerate(article.get('faqs') or []):
        if not isinstance(faq, dict):
            continue
        answer = normal(faq.get('answer', ''))
        if ('autorizacion' in answer and 'se renueva mediante' in answer
                and ('larga duracion' in answer or 'autorizacion de residencia' in answer)):
            problems.append(f'FAQ {i+1}: potential periodic renewal claim for indefinite long-term authorization')
    return list(dict.fromkeys(problems))


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
    # Deterministic scope guard: an initial extraordinary-regularisation application
    # must never be offered as a continuation path to existing authorization holders.
    commercial = plan_obj.get('commercial_classification') or {}
    if commercial.get('business_category') == 'regularizacion_2026':
        text_to_check = ' '.join(
            [str(article.get('introduction',''))] +
            [str(p) for sec in article.get('sections',[]) if isinstance(sec,dict)
             for p in sec.get('paragraphs',[]) if isinstance(p,str)] +
            [str(faq.get('answer','')) for faq in article.get('faqs',[])
             if isinstance(faq,dict)]
        ).lower()
        if re.search(r'(?:para\s+(?:continuar|mantener|prorrogar)\s+(?:su|la)\s+residencia|continuidad\s+(?:de\s+)?(?:su|la)\s+autorizaci[oó]n).{0,180}(?:solicitar|solicitud|acceder\s+a)\s+(?:una?\s+)?(?:autorizaci[oó]n\s+)?(?:de\s+)?arraigo\s+extraordinario', text_to_check, re.I | re.S):
            errors.append('Confused initial extraordinary-regularisation application with post-grant continuity')
        if re.search(r'(?:para\s+solicitar\s+la\s+continuidad|para\s+continuar\s+(?:su|la)\s+residencia).{0,240}(?:antes\s+del\s+1\s+de\s+enero\s+de\s+2026|30\s+de\s+junio\s+de\s+2026|cinco\s+meses\s+de\s+permanencia)', text_to_check, re.I | re.S):
            errors.append('Initial-application eligibility or deadline misapplied to post-grant continuity')
    errors.extend(renewal_scope_warnings(article,plan_obj))
    commercial=plan_obj.get('commercial_classification') or {}
    if commercial and not commercial.get('excluded'):
        title_text=str(article.get('title','')).lower()
        if any(word in title_text for word in ('residencia permanente','larga duración','nacionalidad española','duplicado tie')):
            errors.append('Draft switched to excluded commercial procedure')
        from_title=classify_temporary(article.get('title',''))
        if from_title.get('excluded') or from_title.get('business_category')!=commercial.get('business_category'):
            errors.append('Article title changed outside selected commercial category')
    blob=json.dumps(article,ensure_ascii=False)
    if re.search(r'\[PENDIENTE\]|TODO:|lorem ipsum',blob,re.I):errors.append('Placeholder detected')
    if any(x.get('version_status')=='VERSION_UNCERTAIN' for x in evidence):
        errors.append('One or more provisions have uncertain version dates')
    if not plan_obj['source_registry_complete']:errors.append('Legal source scope not established')
    if plan_obj.get('existing_page_action')=='improve_existing_page':
        errors.append('Existing article has not been reconciled; replacement forbidden')
    return errors


def semantic_review(article,evidence,model='gpt-4.1-mini',client=None,dossier=None,research_coverage=None,research_plan=None):
    claims=article.get('claims',[])
    ids={r['evidence_id']:r for r in evidence}
    annotated=[]
    for i,c in enumerate(claims):
        annotated.append({'claim_index':i,'claim':c.get('claim',''),
            'evidence':[ids[x] for x in c.get('evidence_ids',[]) if x in ids]})
    review_prompt=SYSTEM_REVIEW
    if (research_plan or {}).get('adaptive_editorial_scope'):
        review_prompt += '\nFor an independently approved adaptive scope, assess the NEW authorized title and scope, all approved answers, and explicit original exclusions. Reject any new material legal assertion outside the approved answers or any omitted essential condition or missing approved reader-facing limitation; return scope_limitations_status. Assess completeness relative to the authorized narrow scope, not the historical broad topic. Do not infer impossibility or exceptional-extension eligibility from excluded gaps.'
    resp=call_model([{'role':'system','content':review_prompt},
                     {'role':'user','content':json.dumps({'claims':annotated,'article':article,'all_official_evidence':evidence,'legal_applicability_dossier':dossier,'research_coverage':research_coverage,'research_plan':research_plan},ensure_ascii=False)}],model=model,client=client)
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
    if any(q.get('editorial_exclusions') or q.get('draft_readiness') == 'READY_WITH_DECLARED_LIMITATIONS' for q in (research_coverage or [])):
        if not isinstance(resp.get('gaps'),list):
            problems.append('Reviewer omitted explicit coverage gap list for limited scope')
        if resp.get('scope_limitations_status') != 'SUPPORTED':
            problems.append('Reviewer did not approve editorial scope limitations')
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


def focused_evidence_for_topic(research_plan, evidence):
    """Prefer procedure-specific evidence before independent readiness review.

    For a *national long-term residence card* renewal, unrelated renewal
    provisions cannot establish the card's requirements or filing window.
    This is an evidence-selection guard, NOT a claim of legal verification.
    Other topics retain the ordinary research evidence and approval gates.
    """
    from unicodedata import normalize as unicode_normalize
    import re as _re

    topic = ''.join(c for c in unicode_normalize('NFKD', str(research_plan.get('topic', '')).lower())
                    if not __import__('unicodedata').combining(c))
    is_long_term = research_plan.get('group') == 'renewal' and (
        'permanente' in topic or 'larga duracion' in topic)
    category = research_plan.get('commercial_classification', {}).get('business_category')
    if category == 'regularizacion_2026':
        # Restrict the primary readiness dossier to sources directly concerning
        # post-grant continuity. General renewal provisions and initial arraigo
        # application instructions can introduce legally misleading context.
        selected, excluded = [], []
        for row in evidence:
            article = str(row.get('article') or '')
            source_id = str(row.get('source_id') or '')
            url = str(row.get('official_url') or '').lower()
            title = str(row.get('document_title') or '').lower()
            include = (
                (source_id == 'BOE-A-2024-24099' and article in ('191','74','80','84','86'))
                or (source_id == 'boe' and 'boe-a-2026-8284' in url)
                or (source_id == 'migraciones' and (
                    # Procedure-specific Ministry guidance is admissible as an
                    # UNVERIFIED candidate, not proof that any branch applies.
                    ('55' in title and 'modificaci' in title)
                    or ('ex-26' in title and 'modificaci' in title)
                    or ('criterio de gestión' in title and '191' in title)
                    # The 100-question technical FAQ includes similarly numbered
                    # questions about INITIAL eligibility, not post-grant continuity.
                    # Its excerpts must not be offered as proof of modification.
                    or ('preguntas' in title and 'regularizaci' in title
                        and '100 preguntas' not in title and '100%20preguntas' not in url)
                    or ('preguntas' in url and '.pdf' in url
                        and '100%20preguntas' not in url)
                ))
            )
            if include:
                selected.append(row)
            else:
                excluded.append({'evidence_id': row.get('evidence_id'),
                                 'authority': row.get('authority'),
                                 'article': article,
                                 'reason': 'NOT_POST_GRANT_CONTINUITY_EVIDENCE'})
        return selected, excluded
    if not is_long_term:
        return list(evidence), []

    selected, excluded = [], []
    for row in evidence:
        authority = row.get('authority', '')
        article = str(row.get('article') or '')
        url = str(row.get('official_url', '')).lower()
        title = str(row.get('document_title', '')).lower()
        text = str(row.get('text', '')).lower()
        include = (
            (authority == 'boe' and row.get('source_id') == 'BOE-A-2024-24099'
             and article in ('185', '209'))
            or (authority == 'migraciones' and
                ('larga-duracion' in url or 'larga duración' in title))
            or (authority == 'policia' and
                ('largaduracion' in url or 'larga duración' in title))
        )
        if include:
            selected.append(row)
        else:
            excluded.append({'evidence_id': row.get('evidence_id'),
                             'authority': authority, 'article': article,
                             'reason': 'NOT_TARGET_PROCEDURE_EVIDENCE'})
    return selected, excluded


def _safe_diagnostic(value):
    """Redact configured secrets and recognizable credential strings before persistence."""
    if isinstance(value, dict):
        return {str(k): ('[REDACTED]' if re.search(r'(?i)api.key|authorization|password|secret|token',str(k)) else _safe_diagnostic(v)) for k,v in value.items()}
    if isinstance(value, list):
        return [_safe_diagnostic(v) for v in value]
    if isinstance(value, str):
        for key, secret in os.environ.items():
            if len(secret)>=8 and re.search(r'(?i)key|token|secret|password|credential',key):
                value=value.replace(secret,'[REDACTED]')
        return re.sub(r'(?i)(?:bearer\s+[^\s"\\]+|sk-[a-z0-9_-]{12,}|gh[pousr]_[a-z0-9_]{12,})','[REDACTED]',value)
    return value


def _safe_raw_response(content):
    if not isinstance(content,str):
        return _safe_diagnostic(content)
    # Preserve the original response except for credentials. For valid JSON,
    # redact values under sensitive keys as well as configured secret values.
    safe=_safe_diagnostic(content)
    try:
        parsed=json.loads(safe)
        cleaned=_safe_diagnostic(parsed)
        return safe if cleaned==parsed else json.dumps(cleaned,ensure_ascii=False)
    except (ValueError,TypeError):
        return re.sub(r'(?i)("(?:api[_-]?key|authorization|password|secret|token)"\s*:\s*)"(?:[^"\\]|\\.)*"',r'\1"[REDACTED]"',safe)


def _gap_schema(passage_aliases=None, indices=None):
    fields = {'index':{'type':'integer'},
              'classification':{'type':'string','enum':['MATERIAL','INDIVIDUAL','OPTIONAL_DETAIL','EDITORIAL_EXCLUSION','VERIFIED_BY_MATRIX']},
              'reason':{'type':'string'},'retained_answer':{'type':'string'},
              'limitation':{'type':'string'},'evidence_ids':{'type':'array','items':{'type':'string'}},
              'supporting_passage_ids':{'type':'array','items':{'type':'string'}}}
    if passage_aliases is not None:
        fields.pop('evidence_ids')
        fields['supporting_passage_ids']['items']['enum']=list(passage_aliases)
    if indices is not None:
        fields['index']['enum']=list(indices)
    return {'type':'json_schema','json_schema':{'name':'gap_assessments','strict':True,'schema':{
        'type':'object','additionalProperties':False,'required':['assessments'], 'properties':{
        'assessments':{'type':'array','items':{'type':'object','additionalProperties':False,
                                               'required':list(fields),'properties':fields}}}}}}


def _general_guidance_missing_fact_classification(question, branch_coverage, *,
                                                  plan, evidence, dossier, model, client):
    """Assess gaps independently; never erase coverage or allow invalid rows."""
    facts = question.get('missing_facts') or []
    diagnostic = {'question_id':question.get('id'), 'model':model, 'attempted':False, 'missing_facts':list(facts),
                  'expected_indices':list(range(len(facts))), 'attempts':[], 'rejected':[], 'accepted':[]}
    result = {'individual_case_variables': [], 'non_blocking_unverified_details': [],
              'resolved_by_official_branch_matrix': [], 'editorial_exclusions': [],
              'blocking_missing_facts': list(facts), 'gap_assessments': [], 'gap_diagnostics':diagnostic}
    if not facts or not branch_coverage.get('ready') or question.get('status') != 'PARTIALLY_ANSWERED':
        diagnostic['skip_reason'] = 'NO_GAPS' if not facts else ('BRANCH_COVERAGE_NOT_READY' if not branch_coverage.get('ready') else 'QUESTION_NOT_PARTIAL')
        return result
    aliases = {f'R{i:03d}': r['evidence_id'] for i, r in enumerate(evidence, 1)}
    catalog = build_catalog(evidence)
    selected, omitted = select_context(catalog, evidence, dossier)
    sent = {p['passage_id'] for p in selected}
    passage_aliases, short_selected = short_passage_context(selected)
    diagnostic['passage_alias_map'] = passage_aliases
    if not passage_aliases:
        diagnostic['skip_reason']='NO_SELECTABLE_PASSAGES'
        return result
    diagnostic['passages_sent'] = sorted(sent)
    diagnostic['passages_omitted_for_budget'] = omitted
    if any(not catalog['passages'][pid]['parent_passage_id'] for pid in omitted):
        diagnostic['skip_reason']='CONTEXT_BUDGET_OMITTED_PRIMARY_PASSAGES'
        return result
    compact = [{k:v for k,v in r.items() if k not in ('text','research_relevance')} | {'evidence_id': alias} for alias, r in zip(aliases, evidence)]
    diagnostic['expected_evidence_aliases']=aliases
    prompt = (
        'Independently assess whether each missing fact is essential to the original article intent. '
        'Return a JSON object with assessments array: [{index, classification, reason, retained_answer, limitation, supporting_passage_ids}]. '
        'Classifications: MATERIAL, INDIVIDUAL, OPTIONAL_DETAIL, EDITORIAL_EXCLUSION, VERIFIED_BY_MATRIX. '
        'For MATERIAL identify the specific missing rule, affected assertion and why it cannot be omitted in reason; use limitation for the evidence needed. Do not demand hypothetical additional requirements without a concrete missing rule. Default MATERIAL. Assess the entire gap, not keywords. If any part is material, classify MATERIAL. '
        'EDITORIAL_EXCLUSION only if a general guide can still answer its original intent accurately, '
        'including the conditions and interaction of verified routes, without deciding this separable legal question. '
        'A gap that affects whether exceptional extension is available must not be replaced by a finding that modification '
        'is impossible. If excluding an unresolved route, explicitly require individual verification of that route and '
        'do not assert availability, nonexistence, or eligibility for exceptional extension on that basis. '
        'Consider Article 191.1 as well as specific paragraphs. A focused guide expressly promising the omitted '
        'route, a material deadline, exception, or essential filing step must remain blocked. '
        'INDIVIDUAL means only facts of a real applicant; OPTIONAL_DETAIL means a separable procedural detail, '
        'not an indispensable filing requirement. VERIFIED_BY_MATRIX requires actual official text resolving the gap. '
        'For each non-material classification select supporting_passage_ids from official_passages, using only the exact short passage_id options (P001 etc.) that support the retained answer. Select the smallest sufficient set of passages for the retained answer, including necessary exceptions and conditions; do not select the whole catalog. Never transcribe quotations. Read parent passages for conditions and exceptions. Match legal branch and distinguish procedural guidance from eligibility. For MATERIAL use an empty array if no supporting passage is available. '
        'For each non-material classification provide a concrete retained_answer supported by the selected passage aliases and a limitation stating what must not be concluded. Python derives evidence IDs; do not return them. Never derive passage IDs from evidence IDs. '
        'Do not rewrite questions or change their coverage status.')
    payload = {'topic': plan['topic'], 'original_questions': plan['research_questions'],
               'question': question, 'missing_facts': list(enumerate(facts)),
               'evidence': compact, 'official_passages':short_selected, 'evidence_id_aliases': aliases, 'legal_applicability_dossier': dossier,
               'branch_coverage': branch_coverage}
    diagnostic['attempted']=True
    messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
    response=None
    fallback=None
    for attempt in range(2):
        trace={'attempt':attempt+1,'format':'json_schema'}
        diagnostic['attempts'].append(trace)
        try:
            response=call_model(messages,model=model,client=client,response_format=_gap_schema(passage_aliases,range(len(facts))),diagnostics=trace)
            trace['parsed_response']=_safe_diagnostic(response)
            if not isinstance(response,dict) or not isinstance(response.get('assessments'),list):
                trace['status']='INVALID_RESPONSE'; trace['error_type']='MISSING_ASSESSMENTS_ARRAY'
                response=None
                continue
            trace['status']='PARSED'
            # Retry once if all non-material selections are technically unusable.
            # Keep the first response as fallback; never discard a material finding.
            rows=response['assessments']
            candidates=[r for r in rows if isinstance(r,dict) and r.get('classification')!='MATERIAL']
            bad=[r for r in candidates if not isinstance(r.get('supporting_passage_ids'),list) or
                 not r['supporting_passage_ids'] or any(not isinstance(p,str) or p not in passage_aliases and p not in sent for p in r['supporting_passage_ids'])]
            if attempt==0 and candidates and len(bad)==len(candidates) and len(candidates)==len(rows):
                fallback=response
                trace['selection_retry']='ALL_NONMATERIAL_SELECTIONS_INVALID'
                messages=messages+[{'role':'user','content':'Previous passage selections were invalid. Reassess using only the supplied P001-style aliases from official_passages. Do not invent IDs or change legal findings merely to pass validation.'}]
                continue
            break
        except (json.JSONDecodeError, ValueError) as exc:
            trace['status']='INVALID_RESPONSE'; trace['error_type']=type(exc).__name__; trace['error_message']=_safe_diagnostic(str(exc)[:300])
        except Exception as exc:
            trace['status']='CALL_ERROR'; trace['error_type']=type(exc).__name__
            trace['http_status']=getattr(exc,'code',None)
            trace['error_message']=_safe_diagnostic(str(exc)[:300])
            break
    if response is None and fallback is not None:
        response=fallback
    assessments=response.get('assessments') if isinstance(response,dict) else None
    if not isinstance(assessments,list):
        diagnostic['response_status']='MISSING_ASSESSMENTS_ARRAY'
        diagnostic['rejected']=[{'index':i,'reason':'NO_VALID_RESPONSE'} for i in range(len(facts))]
        return result
    diagnostic['response_status']='ASSESSMENTS_RECEIVED'
    diagnostic['received_indices']=[x.get('index') if isinstance(x,dict) else None for x in assessments]
    by_index={}
    for entry in assessments:
        idx=entry.get('index') if isinstance(entry,dict) else None
        if type(idx) is not int or idx not in range(len(facts)):
            diagnostic['rejected'].append({'index':idx,'reason':'INVALID_INDEX'})
            continue
        by_index.setdefault(idx,[]).append(entry)
    categories = {'INDIVIDUAL':'individual_case_variables', 'OPTIONAL_DETAIL':'non_blocking_unverified_details',
                  'EDITORIAL_EXCLUSION':'editorial_exclusions', 'VERIFIED_BY_MATRIX':'resolved_by_official_branch_matrix'}
    result['blocking_missing_facts'] = []
    canonical_to_alias={v:k for k,v in aliases.items()}
    for idx,fact in enumerate(facts):
        entries=by_index.get(idx,[])
        reason=None
        if len(entries)!=1:
            reason='DUPLICATE_INDEX' if entries else 'MISSING_INDEX'
        else:
            entry=dict(entries[0]); kind=entry.get('classification'); refs=entry.get('evidence_ids')
            raw_ids=entry.get('supporting_passage_ids')
            if isinstance(raw_ids,list):
                entry['supporting_passage_ids']=[passage_aliases.get(x,x) if isinstance(x,str) else x for x in raw_ids]
            if 'evidence_ids' not in entry:
                resolved_ids=[resolve_passage(x,catalog,evidence,allowed_ids=sent) for x in entry.get('supporting_passage_ids',[]) ] if isinstance(raw_ids,list) else []
                refs=list(dict.fromkeys(p['evidence_id'] for p in resolved_ids if p))
                if kind!='MATERIAL' and (not resolved_ids or any(p is None for p in resolved_ids)):
                    diagnostic['rejected'].append({'index':idx,'reason':'INVALID_SUPPORTING_PASSAGE'})
                    result['blocking_missing_facts'].append(fact)
                    continue
            # The dossier includes canonical IDs. Accept only exact known canonical IDs or short aliases.
            if isinstance(refs,list):
                refs=[canonical_to_alias.get(r,r) if isinstance(r,str) else r for r in refs]
            category=categories.get(kind) if isinstance(kind,str) else None
            if not isinstance(refs,list) or any(not isinstance(r,str) or r not in aliases for r in refs):
                reason='INVALID_EVIDENCE_IDS'
            elif not isinstance(entry.get('reason'),str) or not entry['reason'].strip():
                reason='MISSING_REASON'
            elif kind=='MATERIAL':
                result['gap_assessments'].append({**entry,'missing_fact':fact,'evidence_ids':[aliases[r] for r in refs]})
                diagnostic['accepted'].append({'index':idx,'classification':kind,'decision':'BLOCKED'})
                result['blocking_missing_facts'].append(fact)
                continue
            elif not category:
                reason='INVALID_CLASSIFICATION'
            elif not refs or not all(isinstance(entry.get(k),str) and entry[k].strip() for k in ('retained_answer','limitation')):
                reason='MISSING_SUPPORT_OR_LIMITATION'
            elif category=='resolved_by_official_branch_matrix' and not branch_coverage.get('exceptional_extension_conditions_verified'):
                reason='BRANCH_MATRIX_NOT_VERIFIED'
            else:
                passages=entry.get('supporting_passage_ids')
                normalized=[]
                if not isinstance(passages,list) or not passages:
                    reason='MISSING_SUPPORTING_PASSAGES'
                else:
                    seen=set()
                    for pid in passages:
                        resolved=resolve_passage(pid,catalog,evidence,allowed_ids=sent)
                        if not resolved or pid in seen or resolved['evidence_id'] not in {aliases[r] for r in refs}:
                            reason='INVALID_SUPPORTING_PASSAGE'; break
                        seen.add(pid); normalized.append(resolved)
                    if not reason and {p['evidence_id'] for p in normalized} != {aliases[r] for r in refs}:
                        reason='MISSING_PASSAGE_FOR_CITED_EVIDENCE'
                if not reason:
                    entry={**entry,'supporting_passages':normalized}
        if reason:
            diagnostic['rejected'].append({'index':idx,'reason':reason})
            result['blocking_missing_facts'].append(fact)
            continue
        result[category].append(fact)
        result['gap_assessments'].append({**entry,'missing_fact':fact,'evidence_ids':[aliases[r] for r in refs]})
        diagnostic['accepted'].append({'index':idx,'classification':kind,'decision':'LIMITED_SCOPE','passage_ids':entry['supporting_passage_ids']})
    return result


def research_readiness(research_plan,evidence,*,model='gpt-4.1-mini',client=None,dossier=None):
    if not evidence:
        return coverage(research_plan['research_questions'],evidence)
    prompt=('Review each question strictly against supplied official evidence. '
       'Return JSON object with `questions` array of objects id,status,evidence_ids,reason,missing_facts. '
       'For PARTIALLY_ANSWERED, NOT_ANSWERED or REQUIRES_LEGAL_INTERPRETATION, '
       'identify specific missing legal rules or conflicts, not facts about a hypothetical applicant. '
       'For every incomplete question, missing_facts must be a nonempty list of specific unresolved points; do not leave them only in reason. '
       'Start reason with the missing legal rule, then distinguish supporting evidence from the material detail not established. '
       'Only ANSWERED_WITH_EVIDENCE if specific evidence fully answers the legal question with its conditions and exceptions; '
       'otherwise use PARTIALLY_ANSWERED, NOT_ANSWERED, or REQUIRES_LEGAL_INTERPRETATION. '
       'For a GENERAL_GUIDANCE article, applicant-specific variables such as residence duration, origin authorisation, '
       'and work modality are decision branches to explain, not missing research facts. Do not ask for a fictional applicant. '
       'For regularisation 2026, DA20.10 and DA21.10 are separate origins and both expressly enable work by cuenta ajena and propia. '
       'Map Article 191 precisely: 191.2 -> Article 74 for cuenta ajena when the person has not yet resided for at least one year as holder of a residence authorization; '
       '191.3 -> Article 80 for cuenta ajena or Article 86 for cuenta propia when the person has spent at least one year in Spain in a situation of residence and the origin authorisation enabled work; '
       '191.4 -> Article 74 except 1.a and, where applicable, Article 84 only when the origin authorisation did NOT enable work. '
       'Do not treat Articles 74, 80, 84 and 86 as a universal cumulative checklist. For DA20/DA21, Article 84 is not the normal branch because their paragraph 10 enables work. '
       'Do not infer an Article 191 route for cuenta propia before one year if the supplied law does not establish it. '
       'Distinguish extension of validity while a modification is pending from the exceptional extension of the authorisation itself. '
       'A complete universal document checklist or exclusive filing channel is not required for a GENERAL_GUIDANCE article if it is not asserted and is clearly labelled unverified. '
       'The exceptional-extension conditions in DA20.10 and DA21.10 must still be checked and explained from the actual text. '
       'If any material legal rule, exception, deadline or effect needed for the guide is absent or contradictory, keep the question partial or require legal interpretation. '
       'Never invent an evidence_id. This is a research-readiness assessment, not a legal certification.')
    aliases = {f'R{i:03d}': row['evidence_id'] for i, row in enumerate(evidence, 1)}
    prompt_evidence = []
    for alias, row in zip(aliases, evidence):
        compact = dict(row)
        compact['evidence_id'] = alias
        prompt_evidence.append(compact)
    prompt += (' Cite only the exact short evidence_id values supplied in evidence '
               '(for example R001). Never lengthen, guess or concatenate IDs. '
               'For each question, provide evidence_ids as a JSON list; an '
               'unsupported question must not be labelled ANSWERED_WITH_EVIDENCE.')
    result=call_model([{'role':'system','content':prompt},
        {'role':'user','content':json.dumps({'topic':research_plan['topic'],
            'questions':research_plan['research_questions'],
            'evidence':prompt_evidence,'legal_applicability_dossier':dossier},ensure_ascii=False)}],
        model=model,client=client)
    judgments={}
    for item in result.get('questions',[]):
        if not isinstance(item,dict) or not item.get('id'):
            continue
        refs=item.get('evidence_ids',[])
        if not isinstance(refs,list):
            refs=[]
        resolved=[aliases[r] for r in refs if isinstance(r,str) and r in aliases]
        judgments[item['id']]={**item,'evidence_ids':list(dict.fromkeys(resolved))}
    covered, fully_answered = coverage(research_plan['research_questions'],evidence,semantic_judgments=judgments)
    branch_coverage = general_guidance_branch_coverage(evidence, dossier or {})
    general_guide = (branch_coverage.get('applicable') is True)
    if general_guide:
        for question in covered:
            classified = _general_guidance_missing_fact_classification(
                question, branch_coverage, plan=research_plan, evidence=evidence,
                dossier=dossier, model=model, client=client)
            question.update(classified)
            if (question.get('id')=='requirements' and branch_coverage.get('unresolved_legal_branches')
                    and (question.get('status')=='ANSWERED_WITH_EVIDENCE'
                         or (question.get('status')=='PARTIALLY_ANSWERED' and not question.get('missing_facts')
                             and question.get('evidence_ids') and branch_coverage.get('ready')))):
                # A coverage judgment cannot silently erase a known unresolved branch.
                # Preserve the original judgment and require independent scope review.
                for fact in branch_coverage['unresolved_legal_branches']:
                    if fact not in question['blocking_missing_facts']:
                        question['blocking_missing_facts'].append(fact)
                    question['gap_assessments'].append({'classification':'MATERIAL','missing_fact':fact,'reason':'Unresolved legal branch in applicability matrix requires verification or independently narrowed scope, regardless of omitted model gap details.','evidence_ids':[],'origin':'APPLICABILITY_MATRIX'})
                question['gap_diagnostics']['coverage_discrepancy']=list(branch_coverage['unresolved_legal_branches'])
            if question.get('status') == 'ANSWERED_WITH_EVIDENCE' and not question.get('evidence_ids'):
                question['status'] = 'NOT_ANSWERED'
            blocking = question.get('blocking_missing_facts') or []
            has_citations = bool(question.get('evidence_ids'))
            if question.get('status') == 'ANSWERED_WITH_EVIDENCE' and has_citations and not blocking:
                question['draft_readiness'] = 'READY'
            elif question.get('status') == 'PARTIALLY_ANSWERED' and has_citations and not blocking and question.get('missing_facts') and branch_coverage.get('ready'):
                question['draft_readiness'] = 'READY_WITH_DECLARED_LIMITATIONS'
            else:
                question['draft_readiness'] = 'BLOCKED'
                if not question.get('missing_facts') and question.get('status') == 'PARTIALLY_ANSWERED':
                    question['gap_diagnostics']['skip_reason'] = 'INCOMPLETE_JUDGMENT_WITHOUT_MISSING_FACTS'
                    question['gap_diagnostics']['original_reason'] = question.get('reason', '')
                    blocking.append('Partial research without explicit missing facts')
                    question['blocking_missing_facts'] = blocking
                if not has_citations and 'No valid evidence citations for this question' not in blocking:
                    blocking.append('No valid evidence citations for this question')
                    question['blocking_missing_facts'] = blocking
        ready = bool(branch_coverage.get('ready')) and bool(covered) and all(
            q.get('draft_readiness') in ('READY','READY_WITH_DECLARED_LIMITATIONS') for q in covered)
    else:
        for question in covered:
            question['draft_readiness'] = 'READY' if question['status'] == 'ANSWERED_WITH_EVIDENCE' else 'BLOCKED'
            question['blocking_missing_facts'] = question.get('missing_facts', [])
        ready = fully_answered
    for question in covered:
        question['general_guidance_branch_coverage'] = branch_coverage if general_guide else None
    return covered, ready


def partition_retrieval_errors(errors):
    """Optional official-page outages cannot by themselves certify research failure.

    Keep all other errors blocking. Readiness still requires independent
    evidence-based answers for every essential question before drafting.
    """
    warnings = [e for e in errors if e.get('category') == 'OFFICIAL_SOURCE_RETRIEVAL_ERROR']
    blocking = [e for e in errors if e.get('category') != 'OFFICIAL_SOURCE_RETRIEVAL_ERROR']
    return blocking, warnings


def execute(proposals_path,output_path,*,model='gpt-4.1-mini',retrieval=retrieve,client=None,max_revisions=2,max_scope_proposals=3):
    out=Path(output_path);out.mkdir(parents=True,exist_ok=True)
    status={'version':'5.0','publication_allowed':False,'result':'BLOCKED','errors':[],
            'independent_legal_accuracy_verified':False,'live_release_enabled':False}
    def save(name,obj):
        (out/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')
    gap_report={'status':'NOT_REACHED','questions':[],'publication_allowed':False}
    scope_report={'status':'NOT_REACHED','publication_allowed':False}
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
        # Preserve the raw crawl in diagnostics, but do not offer unrelated
        # renewal provisions as evidence for the long-term TIE procedure.
        evidence, excluded_for_topic = focused_evidence_for_topic(research_plan, evidence)
        evidence = split_rd316_evidence(evidence)
        save('evidence_focus.json', {'selected_evidence_ids': [e['evidence_id'] for e in evidence],
             'excluded': excluded_for_topic, 'note': 'Selection does not certify legal applicability'})
        save('evidence.json',evidence);save('retrieval_errors.json',failed)
        save('discovery_diagnostics.json',discovery_diagnostics)
        blocking_errors, source_warnings = partition_retrieval_errors(failed)
        save('retrieval_warnings.json', source_warnings)
        if blocking_errors or not evidence:
            status['errors']=['Evidence retrieval incomplete']+[x.get('details',x.get('detail','')) for x in blocking_errors or failed]
            status['result']='BLOCKED_INSUFFICIENT_EVIDENCE'
            status['failure_codes']=[x.get('category') for x in blocking_errors or failed]
            return 2
        save('evidence_passage_catalog.json',build_catalog(evidence))
        dossier=build_dossier(research_plan,evidence)
        covered,ready=research_readiness(research_plan,evidence,model=model,client=client,dossier=dossier)
        gap_report.update({'status':'EVALUATED','questions':[{'question_id':q.get('id'), 'diagnostics':q.get('gap_diagnostics',{'attempted':False,'skip_reason':'NOT_GENERAL_GUIDANCE'}),'blocking_missing_facts':q.get('blocking_missing_facts',[]),'draft_readiness':q.get('draft_readiness')} for q in covered], 'ready_before_applicability':ready})
        for q in covered:
            q.pop('gap_diagnostics',None)
        graph=build_source_claims(evidence,dossier,covered)
        graph['distinct_legal_mechanisms']=operative_mechanisms(evidence)
        graph_errors=validate_graph(graph,dossier,evidence)
        save('legal_applicability.json',dossier)
        save('source_claim_graph.json',graph)
        matrix=question_matrix(research_plan,evidence,covered,dossier)
        matrix['source_claims']=graph['source_claims']
        matrix['graph_integrity_errors']=graph_errors
        save('claim_evidence_matrix.json',matrix)
        gap_report['graph_integrity_errors']=graph_errors
        gap_report['applicability_conflicts']=scope_conflicts(matrix)
        if graph_errors:
            gap_report['ready_for_draft']=False
            status['result']='BLOCKED_APPLICABILITY'
            status['errors']=graph_errors
            return 2
        if scope_conflicts(matrix):
            ready=False
        general_guide = dossier.get('procedure_context', {}).get('editorial_scope') == 'GENERAL_GUIDANCE'
        save('research_coverage.json',{'questions':covered,'ready':ready,
             'ready_for_draft':ready,
             'coverage_fully_answered':all(q.get('status') == 'ANSWERED_WITH_EVIDENCE' and not q.get('blocking_missing_facts') for q in covered),
             'model_coverage_fully_answered':all(q.get('status') == 'ANSWERED_WITH_EVIDENCE' for q in covered),
             'draft_readiness_mode':('GENERAL_GUIDANCE_WITH_DECLARED_LIMITATIONS' if general_guide and ready else 'FULL_EVIDENCE_REQUIRED'),
             'human_legal_review_required':True,
             'legal_accuracy_certified':False,
             'applicability_conflicts':scope_conflicts(matrix),
             'publication_allowed':False})
        gap_report['ready_for_draft']=ready
        if not ready:
            alternative=None
            if not scope_conflicts(matrix):
                alternative=alternative_scope(research_plan,covered,evidence,dossier,call=call_model,model=model,client=client,report=scope_report,max_proposals=max_scope_proposals)
            else:
                scope_report['status']='BLOCKED_ORIGINAL_APPLICABILITY'
            if alternative:
                alt_plan,alt_covered=alternative
                # Reapply metadata-only duplicate detection to the new title.
                try:
                    from seo_v50 import classify_duplicate, metadata_inventory
                except ImportError:
                    from scripts.seo_v50 import classify_duplicate, metadata_inventory
                duplicate,duplicate_reason,_=classify_duplicate({'proposed_title':alt_plan['topic'],'primary_query':alt_plan['commercial_classification']['search_intent']},metadata_inventory(Path(__file__).resolve().parents[1]))
                alt_dossier=build_dossier(alt_plan,evidence)
                alt_matrix=question_matrix(alt_plan,evidence,alt_covered,alt_dossier)
                alt_graph=build_source_claims(evidence,alt_dossier,alt_covered)
                alt_graph['distinct_legal_mechanisms']=operative_mechanisms(evidence)
                alt_errors=scope_conflicts(alt_matrix)+validate_graph(alt_graph,alt_dossier,evidence)
                if duplicate:
                    alt_errors.append('ALTERNATIVE_DUPLICATE_METADATA: '+duplicate_reason)
                if alt_errors:
                    scope_report.update({'status':'BLOCKED_ALTERNATIVE_APPLICABILITY','errors':alt_errors})
                    alternative=None
                else:
                    research_plan,covered,dossier=alt_plan,alt_covered,alt_dossier
                    save('alternative_claim_evidence_matrix.json',alt_matrix)
                    save('alternative_source_claim_graph.json',alt_graph)
                    gap_report['alternative_ready_for_draft']=True
                    gap_report['original_scope_ready_for_draft']=False
                    status['adaptive_editorial_scope']=True
            if not alternative:
                status['result']='BLOCKED_INSUFFICIENT_EVIDENCE'
                status['errors']=['Official provisions do not answer every essential research question']
                return 2
        else:
            scope_report['status']='ORIGINAL_SCOPE_READY'
        audit=[];draft=None
        for attempt in range(max_revisions+1):
            previous=draft
            draft=article_request(research_plan,evidence,model=model,client=client,previous=previous,
                    findings=audit[-1] if audit else None,dossier=dossier,research_coverage=covered)
            integrity=verify_integrity(draft,evidence,research_plan)
            if research_plan.get('adaptive_editorial_scope') and draft.get('title')!=research_plan['topic']:
                integrity.append('Draft changed the independently authorized alternative title')
            claim_matrix,claim_errors=audit_declared_claims(draft,dossier)
            integrity.extend(claim_errors)
            save('article_claim_applicability.json',claim_matrix)
            review,review_errors=semantic_review(draft,evidence,model=model,client=client,dossier=dossier,research_coverage=covered,research_plan=research_plan) if not any('unknown evidence ID' in x for x in integrity) else ({'assessment':[]},['Invalid citations'])
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
        status['errors']=[type(exc).__name__+': '+_safe_diagnostic(str(exc)[:250])]
        status['result']='ERROR'
        return 4
    finally:
        if gap_report['status']=='NOT_REACHED':
            gap_report['skip_reason']='PIPELINE_EXIT_BEFORE_GAP_ASSESSMENT'
        gap_report['final_result']=status['result']
        gap_report['final_errors']=_safe_diagnostic(status['errors'])
        save('gap_assessment_diagnostics.json',_safe_diagnostic(gap_report))
        save('passage_selection_diagnostics.json',_safe_diagnostic(gap_report))
        scope_report['final_result']=status['result']
        save('editorial_scope_decision.json',_safe_diagnostic(scope_report))
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
