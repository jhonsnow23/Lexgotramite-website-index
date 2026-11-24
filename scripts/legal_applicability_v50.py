#!/usr/bin/env python3
"""Conservative, auditable legal applicability dossier for Lex Go Trámite v5.0.

Classification is a *research hypothesis*, never legal certification. In
particular, cross-references do not establish requirements for every route.
No network, external content, or blog bodies are accessed by this module.
"""
from __future__ import annotations
from datetime import datetime, timezone
import re
import unicodedata

CATEGORIES = frozenset({
    'regularizacion_2026', 'arraigo', 'cuenta_ajena', 'cuenta_propia',
    'no_lucrativa', 'menores_no_nacidos',
})
APPLICABILITY = frozenset({
    'DIRECTLY_APPLICABLE', 'CONDITIONALLY_APPLICABLE', 'PROCEDURAL_GUIDANCE',
    'CONTEXT_ONLY', 'UNRELATED', 'UNDETERMINED',
})


def normalize(value):
    s = unicodedata.normalize('NFKD', str(value or '').lower())
    return ' '.join(re.findall(r'[a-z0-9]+', ''.join(c for c in s if not unicodedata.combining(c))))


def procedure_context(plan):
    c = plan.get('commercial_classification') or {}
    cat = c.get('business_category')
    if cat not in CATEGORIES or c.get('excluded'):
        raise ValueError('OUT_OF_SCOPE_OR_UNCLASSIFIED_PROCEDURE')
    scope = ('GENERAL_GUIDANCE' if cat == 'regularizacion_2026' and
             not any(t in normalize(plan.get('topic')) for t in
                     ('mi caso particular', 'mi expediente', 'consulta individual'))
             else 'PROCEDURE_SPECIFIC')
    legal_regime = ('REGULARIZACION_EXTRAORDINARIA_2026' if cat == 'regularizacion_2026'
                    else 'ARRAIGO_MODALIDAD_POR_DETERMINAR' if cat == 'arraigo'
                    else 'RESIDENCIA_TEMPORAL_' + cat.upper())
    kind = c.get('procedure_type') or 'TO_BE_DETERMINED_FROM_OFFICIAL_SOURCES'
    routes = []
    if cat == 'regularizacion_2026':
        routes = [
            {'route_id':'MODIFICACION_ART_191', 'procedure_type':'MODIFICACION',
             'destination_authorization':'SEGUN_ACTIVIDAD_Y_SUPUESTO',
             'conditions':'Debe analizarse la modalidad concreta del artículo 191 y la autorización de origen',
             'verification_status':'NOT_VERIFIED_FOR_INDIVIDUAL'},
            {'route_id':'PRORROGA_EXCEPCIONAL', 'procedure_type':'PRORROGA',
             'destination_authorization':'AUTORIZACION_EXTRAORDINARIA_SI_PROCEDE',
             'conditions':'Solo cuando concurra el supuesto excepcional confirmado por normativa y guía aplicables',
             'verification_status':'NOT_VERIFIED_FOR_INDIVIDUAL'},
        ]
    else:
        routes = [{'route_id':cat.upper()+'_PROCEDURE', 'procedure_type':kind,
                   'destination_authorization':'PENDING_PROCEDURE_SPECIFIC_RESEARCH',
                   'conditions':'Consultar modalidad, vigencia y circunstancias individuales',
                   'verification_status':'NOT_VERIFIED_FOR_INDIVIDUAL'}]
    return {
        'business_category':cat, 'legal_regime':legal_regime,
        'editorial_scope':scope, 'origin_authorization':(
            'AUTORIZACION_EXTRAORDINARIA_2026_YA_CONCEDIDA' if cat == 'regularizacion_2026'
            else 'AUTORIZACION_TEMPORAL_'+cat.upper()),
        'procedure_type':kind, 'routes':routes,
        'discovery_group_legacy':plan.get('group'),
        'note':'El grupo técnico de descubrimiento no constituye clasificación jurídica',
    }


def _role(row, context):
    """Do not infer legal applicability solely from a keyword or source title."""
    category = context['business_category']
    source = str(row.get('source_id') or '')
    article = str(row.get('article') or '')
    title = normalize(row.get('document_title'))
    url = normalize(row.get('official_url'))
    text = normalize(row.get('text'))
    hint = row.get('research_relevance') or {}
    if hint.get('context_only'):
        return 'CONTEXT_ONLY', [], 'Referencia cruzada: exige comprobar la vía de destino'
    if category == 'regularizacion_2026':
        if source == 'BOE-A-2024-24099':
            if article == '191':
                return ('CONDITIONALLY_APPLICABLE', ['MODIFICACION_ART_191'],
                        'Regula distintas modalidades de modificación; no todas se aplican simultáneamente')
            if article in ('74','80','84','86'):
                return ('CONTEXT_ONLY', [], 'Norma referenciada: requisitos dependientes del supuesto jurídico')
            return 'UNRELATED', [], 'Artículo no identificado como vía de continuidad extraordinaria'
        if 'boe a 2026 8284' in url:
            if any(x in text for x in ('modific', 'prorrog', 'continuidad', 'vigencia')):
                return ('CONDITIONALLY_APPLICABLE', ['MODIFICACION_ART_191', 'PRORROGA_EXCEPCIONAL'],
                        'Verificar disposición y párrafo sobre continuidad, no requisitos de acceso inicial')
            return 'CONTEXT_ONLY', [], 'Decreto modificador sin pasaje específico de continuidad en este fragmento'
        if source == 'migraciones':
            if 'ex 26' in title:
                return ('PROCEDURAL_GUIDANCE', ['MODIFICACION_ART_191'],
                        'Formulario para modificación, no acreditación de elegibilidad')
            if 'hoja 55' in title or 'modificacion' in title or 'modificaci' in title:
                return ('PROCEDURAL_GUIDANCE', ['MODIFICACION_ART_191'],
                        'Guía de modificación sujeta a correspondencia con autorización de origen')
            if 'criterio' in title and ('191' in title or '191' in text):
                return ('CONDITIONALLY_APPLICABLE', ['MODIFICACION_ART_191'],
                        'Criterio de gestión; comprobar apartado concreto y vigencia')
            if ('preguntas' in title or 'faq' in title) and any(x in text for x in ('prorrog', 'modific')):
                return ('PROCEDURAL_GUIDANCE', ['MODIFICACION_ART_191','PRORROGA_EXCEPCIONAL'],
                        'Guía ministerial; comprobar que el fragmento trate el periodo posterior a la concesión')
            return 'CONTEXT_ONLY', [], 'Guía sin atribución segura a continuidad posterior'
        return 'UNDETERMINED', [], 'Se requiere comprobar autoridad, procedimiento y párrafo concreto'
    # Other categories: evidence retrieved is not automatically directly applicable.
    if source == 'BOE-A-2024-24099' and article:
        return ('CONDITIONALLY_APPLICABLE', [context['routes'][0]['route_id']],
                'Comprobar la modalidad y los presupuestos específicos del precepto')
    if source in ('migraciones','policia','boe'):
        return ('PROCEDURAL_GUIDANCE' if source == 'migraciones' else 'UNDETERMINED',
                [context['routes'][0]['route_id']] if source == 'migraciones' else [],
                'Pendiente de verificar correspondencia exacta con el procedimiento')
    return 'UNDETERMINED', [], 'Sin relación normativa específica acreditada'


def build_dossier(plan, evidence):
    context=procedure_context(plan)
    annotated=[]; buckets={k:[] for k in APPLICABILITY}
    for row in evidence:
        role,routes,reason=_role(row,context)
        assert role in APPLICABILITY
        eid=row['evidence_id']
        tagged = {
            'evidence_id':eid,
            'source_url':row.get('official_url'), 'issuing_authority':row.get('authority'),
            'source_type':'LEGISLATION' if row.get('authority')=='boe' else 'OFFICIAL_GUIDANCE',
            'legal_reference':{'document':row.get('source_id'),'article':row.get('article')},
            'legal_version':row.get('version_date'),
            'retrieved_at':row.get('retrieved_at'),
            'business_category':context['business_category'], 'legal_regime':context['legal_regime'],
            'origin_authorization':context['origin_authorization'],
            'destination_authorization':routes,
            'procedure_type':context['procedure_type'],
            'procedure_stage':'POST_GRANT_CONTINUITY',
            'applicability':role,'applicability_conditions':[reason],
            'supported_claims':[], 'limitations':[reason],
            'verification_status':'UNVERIFIED_APPLICABILITY',
        }
        annotated.append(tagged);buckets[role].append(eid)
    return {'schema_version':'1.0','procedure_context':context,
            'applicability_evidence':annotated,
            'buckets':buckets,
            'legal_accuracy_certified':False,
            'publication_allowed':False}


def question_matrix(plan, evidence, coverage_questions, dossier):
    by_id={row['evidence_id']:row for row in dossier['applicability_evidence']}
    answer=[]
    for q in coverage_questions:
        relations=[]; conflicts=[]
        for eid in q.get('evidence_ids') or []:
            record=by_id.get(eid)
            if not record:
                conflicts.append('UNKNOWN_EVIDENCE_ID:'+str(eid));continue
            relations.append({'evidence_id':eid,'applicability':record['applicability'],
                              'route_ids':record['destination_authorization'],
                              'limitations':record['limitations']})
            if record['applicability'] in ('UNRELATED','UNDETERMINED'):
                conflicts.append('EVIDENCE_APPLICABILITY_NOT_ESTABLISHED:'+eid)
        answer.append({'question_id':q['id'], 'status':q.get('status'),
                       'claim_text':q.get('question'), 'evidence_relations':relations,
                       'missing_facts':q.get('missing_facts',[]),
                       'applicability_conflicts':conflicts,
                       'next_research_action':('Resolve listed missing facts in the specific legal branch'
                            if q.get('status')!='ANSWERED_WITH_EVIDENCE' or conflicts else 'Independent full-article review required')})
    return {'schema_version':'1.0','questions':answer,
            'publication_allowed':False,'legal_accuracy_certified':False}


def scope_conflicts(question_matrix_obj):
    return [f"{x['question_id']}: {c}" for x in question_matrix_obj.get('questions',[])
            for c in x['applicability_conflicts']]


def audit_declared_claims(article, dossier):
    """Deterministic second gate: contextual material alone cannot substantiate a claim.

    This supplements, but never replaces, semantic full-article review. A
    claim with mixed evidence can still be rejected by the independent reviewer.
    """
    by_id={r['evidence_id']:r for r in dossier.get('applicability_evidence',[])}
    rows=[];errors=[]
    for i,claim in enumerate(article.get('claims') or [],1):
        if not isinstance(claim,dict):
            errors.append(f'Claim {i}: invalid claim object');continue
        ids=claim.get('evidence_ids') or []
        roles=[by_id[eid]['applicability'] for eid in ids if eid in by_id]
        valid=(len(roles)==len(ids) and bool(roles) and
               any(r in ('DIRECTLY_APPLICABLE','CONDITIONALLY_APPLICABLE','PROCEDURAL_GUIDANCE') for r in roles))
        rows.append({'claim_index':i-1,'claim':claim.get('claim'),
                     'evidence_ids':ids,'applicability_roles':roles,
                     'requires_independent_review':True,'context_only_or_unknown':not valid})
        if not valid:
            errors.append(f'Claim {i}: evidence is contextual, unknown or unrelated to target procedure')
    return {'claims':rows,'legal_accuracy_certified':False}, errors
