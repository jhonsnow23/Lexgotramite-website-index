#!/usr/bin/env python3
"""Conservative, auditable legal applicability dossier for Lex Go Trámite v5.0.

The regularisation-2026 branch map below follows the explicit cross-references
in RD 1155/2024 art. 191 and the work authorisation stated in DA20.10/DA21.10.
It describes legal branches for a GENERAL GUIDE; it does not decide an
individual applicant's eligibility or certify legal accuracy.
"""
from __future__ import annotations
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

RD1155 = 'BOE-A-2024-24099'
RD316 = 'BOE-A-2026-8284'

# Explicit branches in RD 1155/2024 art. 191 for holders of DA20/DA21
# authorisations, whose para. 10 expressly enables work on an employed and
# self-employed basis.
ARTICLE_191_BRANCHES = (
    {
        'route_id': 'MOD_ART191_2_AJENA_LT_1Y',
        'article_191_paragraph': '191.2',
        'destination_work_modality': 'CUENTA_AJENA',
        'residence_duration': 'LESS_THAN_ONE_YEAR_AS_RESIDENCE_HOLDER',
        'origin_authorization_must_enable_work': None,
        'requirements_reference': '74',
        'applicability': 'CONDITIONALLY_APPLICABLE',
        'condition': 'La persona solicita residencia y trabajo por cuenta ajena y aún no lleva residiendo al menos un año como titular de una autorización de residencia.',
    },
    {
        'route_id': 'MOD_ART191_3_AJENA_GE_1Y',
        'article_191_paragraph': '191.3',
        'destination_work_modality': 'CUENTA_AJENA',
        'residence_duration': 'AT_LEAST_ONE_YEAR',
        'origin_authorization_must_enable_work': True,
        'requirements_reference': '80',
        'applicability': 'CONDITIONALLY_APPLICABLE',
        'condition': 'La persona lleva al menos un año en España en situación de residencia y la autorización de origen ya habilitaba a trabajar.',
    },
    {
        'route_id': 'MOD_ART191_3_PROPIA_GE_1Y',
        'article_191_paragraph': '191.3',
        'destination_work_modality': 'CUENTA_PROPIA',
        'residence_duration': 'AT_LEAST_ONE_YEAR',
        'origin_authorization_must_enable_work': True,
        'requirements_reference': '86',
        'applicability': 'CONDITIONALLY_APPLICABLE',
        'condition': 'La persona lleva al menos un año en España en situación de residencia y la autorización de origen ya habilitaba a trabajar por cuenta ajena o propia.',
    },
)

# Art. 191.4 is a separate branch for an origin authorisation that did NOT
# permit work. DA20.10 and DA21.10 expressly permit both work modalities, so
# this is not the ordinary branch for either 2026 extraordinary authorisation.
ARTICLE_191_NO_WORK_BRANCH = {
    'route_id': 'MOD_ART191_4_ORIGIN_NO_WORK',
    'article_191_paragraph': '191.4',
    'requirements_references': ['74_except_1a', '84_if_applicable'],
    'applicability_to_DA20_DA21': 'NOT_APPLICABLE_TO_THESE_WORK_ENABLED_ORIGINS',
    'condition': 'Solo para autorizaciones de origen que no habilitaban a trabajar; no trasladar a titulares DA20/DA21, que sí habilitan trabajo.',
}


def normalize(value):
    s = unicodedata.normalize('NFKD', str(value or '').lower())
    return ' '.join(re.findall(r'[a-z0-9]+', ''.join(c for c in s if not unicodedata.combining(c))))


def _regularisation_routes():
    routes = [
        {'route_id': 'MODIFICACION_ART_191', 'procedure_type': 'MODIFICACION',
         'destination_authorization': 'SEGUN_MODALIDAD_Y_TIEMPO_DE_RESIDENCIA',
         'conditions': 'La modalidad concreta depende de la duración de residencia, de la autorización de origen y del tipo de trabajo de destino.',
         'verification_status': 'LEGAL_BRANCHES_MAPPED_INDIVIDUAL_FACTS_NOT_ASSESSED'},
    ]
    for branch in ARTICLE_191_BRANCHES:
        routes.append({**branch, 'procedure_type': 'MODIFICACION',
                       'destination_authorization': branch['destination_work_modality'],
                       'verification_status': 'CONDITIONAL_RULE_MAPPED_NOT_INDIVIDUAL_ELIGIBILITY'})
    routes.extend([
        {'route_id': 'MOD_ART191_4_ORIGIN_NO_WORK', 'procedure_type': 'MODIFICACION',
         'destination_authorization': 'CUENTA_AJENA_OR_PROPIA',
         'conditions': ARTICLE_191_NO_WORK_BRANCH['condition'],
         'requirements_references': ARTICLE_191_NO_WORK_BRANCH['requirements_references'],
         'applicability_to_DA20_DA21': 'NOT_APPLICABLE_TO_THESE_WORK_ENABLED_ORIGINS',
         'verification_status': 'EXCLUDED_FOR_DA20_DA21_ORIGIN'},
        {'route_id': 'MOD_CUENTA_PROPIA_LT_1Y_UNRESOLVED', 'procedure_type': 'MODIFICACION',
         'destination_authorization': 'CUENTA_PROPIA',
         'conditions': 'El apartado 191.2 regula expresamente cuenta ajena y el 191.3 exige al menos un año; no inferir una vía de cuenta propia antes del año sin base adicional.',
         'verification_status': 'UNRESOLVED_REQUIRES_LEGAL_REVIEW'},
        {'route_id': 'EXTENSION_VALIDEZ_DURANTE_MODIFICACION', 'procedure_type': 'EFECTO_DE_PRESENTACION',
         'destination_authorization': 'AUTORIZACION_DE_ORIGEN',
         'conditions': 'La presentación de la modificación en los plazos previstos prolonga la validez de la autorización anterior hasta la resolución; no es la prórroga excepcional de la autorización.',
         'verification_status': 'RULE_STATED_IN_DA20_10_AND_DA21_10'},
        {'route_id': 'PRORROGA_EXCEPCIONAL_1Y', 'procedure_type': 'PRORROGA',
         'destination_authorization': 'AUTORIZACION_EXTRAORDINARIA_DE_ORIGEN',
         'conditions': 'Solo si no se pudiera solicitar modificación; búsqueda activa de empleo e inscripción en el servicio público de empleo, o informe autonómico de esfuerzo de integración que recomiende la prórroga.',
         'duration': 'UN_YEAR',
         'verification_status': 'RULE_STATED_IN_DA20_10_AND_DA21_10'},
        {'route_id': 'PRORROGA_EXCEPCIONAL_4Y', 'procedure_type': 'PRORROGA',
         'destination_authorization': 'AUTORIZACION_EXTRAORDINARIA_DE_ORIGEN',
         'conditions': 'Excepción a los requisitos ordinarios de búsqueda activa/informe cuando concurran los impedimentos de acceso al empleo expresamente previstos, incluida enfermedad grave o discapacidad en los supuestos descritos o edad legal de jubilación.',
         'duration': 'FOUR_YEARS',
         'verification_status': 'RULE_STATED_IN_DA20_10_AND_DA21_10'},
        {'route_id': 'PRORROGA_EXCEPCIONAL', 'procedure_type': 'PRORROGA',
         'destination_authorization': 'AUTORIZACION_EXTRAORDINARIA_DE_ORIGEN',
         'conditions': 'Vía excepcional distinta de la prolongación de validez durante la tramitación de una modificación.',
         'verification_status': 'RULE_STATED_IN_DA20_10_AND_DA21_10'},
    ])
    return routes


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
    if cat == 'regularizacion_2026':
        origins = [
            {'origin_authorization_id': 'DA20_ARRAIGO_SOCIAL',
             'legal_reference': 'RD 1155/2024, disposición adicional vigésima, apartado 10',
             'work_authorized': ['CUENTA_AJENA', 'CUENTA_PROPIA']},
            {'origin_authorization_id': 'DA21_ARRAIGO_EXTRAORDINARIO',
             'legal_reference': 'RD 1155/2024, disposición adicional vigesimoprimera, apartado 10',
             'work_authorized': ['CUENTA_AJENA', 'CUENTA_PROPIA']},
        ]
        routes = _regularisation_routes()
        decision_variables = [
            'Disposición de origen: DA20 o DA21.',
            '191.2: tiempo residiendo como titular de una autorización de residencia; 191.3 y 191.4: tiempo en España en situación de residencia. No equiparar ambos criterios.',
            'Modalidad de destino: cuenta ajena o cuenta propia.',
            'Si la autorización de origen habilitaba a trabajar (DA20.10 y DA21.10 sí lo hacen).',
            'Si se puede solicitar modificación o concurre el supuesto excepcional de prórroga.',
        ]
        unresolved_branches = [
            'La aplicación del artículo 191 a una modificación por cuenta propia antes de cumplir un año no debe inferirse de los apartados 191.2 o 191.3; requiere comprobación jurídica específica.'
        ]
    else:
        origins = [{'origin_authorization_id': 'AUTORIZACION_TEMPORAL_' + cat.upper(),
                    'legal_reference': None, 'work_authorized': None}]
        routes = [{'route_id': cat.upper() + '_PROCEDURE', 'procedure_type': kind,
                   'destination_authorization': 'PENDING_PROCEDURE_SPECIFIC_RESEARCH',
                   'conditions': 'Consultar modalidad, vigencia y circunstancias individuales',
                   'verification_status': 'NOT_VERIFIED_FOR_INDIVIDUAL'}]
        decision_variables = ['Modalidad concreta de autorización y circunstancias del supuesto.']
        unresolved_branches = []
    try:
        from temporary_residence_policy_v50 import catalonia_social_focus
    except ImportError:
        from scripts.temporary_residence_policy_v50 import catalonia_social_focus
    return {
        'regional_report_scope': 'CATALONIA' if catalonia_social_focus(cat,plan.get('topic','')) else None,
        'business_category': cat, 'legal_regime': legal_regime,
        'editorial_scope': scope,
        'origin_authorization': ('DA20_OR_DA21_TEMPORARY_RESIDENCE_AUTHORIZATION'
                                 if cat == 'regularizacion_2026'
                                 else origins[0]['origin_authorization_id']),
        'origin_authorizations': origins,
        'origin_work_authorized_modalities': ['CUENTA_AJENA', 'CUENTA_PROPIA'] if cat == 'regularizacion_2026' else None,
        'procedure_type': kind, 'routes': routes,
        'decision_variables': decision_variables,
        'unresolved_legal_branches': unresolved_branches,
        'discovery_group_legacy': plan.get('group'),
        'note': 'El grupo técnico de descubrimiento no constituye clasificación jurídica',
    }


def _role(row, context):
    """Assign a source to a legal branch only where the cited rule supports it."""
    category = context['business_category']
    source = str(row.get('source_id') or '')
    article = str(row.get('article') or '')
    title = normalize(row.get('document_title'))
    url = normalize(row.get('official_url'))
    text = normalize(row.get('text'))
    hint = row.get('research_relevance') or {}

    if category == 'regularizacion_2026':
        # Explicit Article 191 cross-references override the generic retrieval
        # hint context_only=True. Their relevance is conditional and branch-bound.
        if source == RD1155:
            if article == '191':
                routes = ['MODIFICACION_ART_191'] + [x['route_id'] for x in ARTICLE_191_BRANCHES] + ['MOD_ART191_4_ORIGIN_NO_WORK']
                return ('CONDITIONALLY_APPLICABLE', routes,
                        'Artículo 191: ramas distintas según tiempo de residencia, modalidad de destino y habilitación para trabajar de la autorización de origen.')
            if article == '74':
                return ('CONDITIONALLY_APPLICABLE', ['MOD_ART191_2_AJENA_LT_1Y'],
                        'Remisión expresa del artículo 191.2: el contenido del artículo 74 se incorpora solo a la rama de cuenta ajena cuando aún no se lleva al menos un año como titular; no es una solicitud inicial ni un requisito universal.')
            if article == '80':
                return ('CONDITIONALLY_APPLICABLE', ['MOD_ART191_3_AJENA_GE_1Y'],
                        'Remisión expresa del artículo 191.3: el artículo 80 aporta requisitos para la modificación por cuenta ajena cuando se lleva al menos un año y el origen habilitaba a trabajar; no es una solicitud autónoma de renovación.')
            if article == '86':
                return ('CONDITIONALLY_APPLICABLE', ['MOD_ART191_3_PROPIA_GE_1Y'],
                        'Remisión expresa del artículo 191.3: el artículo 86 aporta requisitos para la modificación por cuenta propia cuando se lleva al menos un año y el origen habilitaba a trabajar; no es una solicitud autónoma de renovación.')
            if article == '84':
                return ('CONTEXT_ONLY', [],
                        'El artículo 84 se relaciona con la rama del artículo 191.4 para autorizaciones de origen que no habilitaban a trabajar; DA20.10 y DA21.10 sí habilitan ambas modalidades de trabajo, por lo que no se aplica a estos orígenes.')
            if hint.get('context_only'):
                return ('CONTEXT_ONLY', [], 'Referencia cruzada no asignada a una rama aplicable a DA20/DA21.')
            return ('UNRELATED', [], 'Artículo no identificado como aplicable a la continuidad DA20/DA21.')

        if source == RD316 or RD316.lower() in url:
            if article in ('DA20.10', 'DA21.10'):
                origin = 'DA20_ARRAIGO_SOCIAL' if article == 'DA20.10' else 'DA21_ARRAIGO_EXTRAORDINARIO'
                return ('CONDITIONALLY_APPLICABLE', [
                    'MODIFICACION_ART_191', 'EXTENSION_VALIDEZ_DURANTE_MODIFICACION',
                    'PRORROGA_EXCEPCIONAL', 'PRORROGA_EXCEPCIONAL_1Y', 'PRORROGA_EXCEPCIONAL_4Y'
                ], 'Apartado 10 de la disposición de origen: habilita a trabajar por cuenta ajena y propia y regula modificación, prolongación de validez durante la tramitación y prórroga excepcional.', origin)
            if any(x in text for x in ('modific', 'prorrog', 'continuidad', 'vigencia')):
                return ('CONDITIONALLY_APPLICABLE', ['MODIFICACION_ART_191', 'PRORROGA_EXCEPCIONAL'],
                        'Decreto oficial: comprobar la disposición y el apartado operativo concretos.')
            return ('CONTEXT_ONLY', [], 'Decreto modificador sin pasaje específico de continuidad en este fragmento')

        if source == 'migraciones':
            if 'ex 26' in title:
                return ('PROCEDURAL_GUIDANCE', [
                    'MODIFICACION_ART_191', 'MOD_ART191_2_AJENA_LT_1Y',
                    'MOD_ART191_3_AJENA_GE_1Y', 'MOD_ART191_3_PROPIA_GE_1Y'
                ], 'Formulario EX-26: modelo de solicitud y opciones declaradas; no acredita elegibilidad ni canal exclusivo.')
            if 'hoja 55' in title or 'modificacion' in title or 'modificaci' in title:
                routes = ['MODIFICACION_ART_191', 'MOD_ART191_2_AJENA_LT_1Y',
                          'MOD_ART191_3_AJENA_GE_1Y', 'MOD_ART191_3_PROPIA_GE_1Y']
                return ('PROCEDURAL_GUIDANCE', routes,
                        'Guía ministerial sobre modificación desde autorizaciones que habilitan a trabajar; contrastar cada requisito con la rama del artículo 191.')
            if 'criterio' in title and ('191' in title or '191' in text):
                routes = ['MODIFICACION_ART_191', 'MOD_ART191_2_AJENA_LT_1Y',
                          'MOD_ART191_3_AJENA_GE_1Y', 'MOD_ART191_3_PROPIA_GE_1Y']
                if 'prorrog' in text:
                    routes.extend(['PRORROGA_EXCEPCIONAL', 'PRORROGA_EXCEPCIONAL_1Y', 'PRORROGA_EXCEPCIONAL_4Y'])
                return ('PROCEDURAL_GUIDANCE', routes,
                        'Criterio de gestión: utilizar solo los apartados que coincidan con la vía y verificar vigencia.')
            if ('preguntas' in title or 'faq' in title) and any(x in text for x in ('prorrog', 'modific')):
                routes = ['MODIFICACION_ART_191', 'PRORROGA_EXCEPCIONAL']
                return ('PROCEDURAL_GUIDANCE', routes,
                        'Guía ministerial: comprobar que cada fragmento trate la fase posterior a la concesión.')
            return ('CONTEXT_ONLY', [], 'Guía sin atribución segura a continuidad posterior')

        return ('UNDETERMINED', [], 'Se requiere comprobar autoridad, procedimiento y párrafo concreto')

    # Preserve conservative behaviour for the other five commercial categories.
    if hint.get('context_only'):
        return 'CONTEXT_ONLY', [], 'Referencia cruzada: exige comprobar la vía de destino'
    if source == RD1155 and article:
        return ('CONDITIONALLY_APPLICABLE', [context['routes'][0]['route_id']],
                'Comprobar la modalidad y los presupuestos específicos del precepto')
    if source == 'gencat':
        try:
            from official_sources_v50 import CAT_INTEGRATION
        except ImportError:
            from scripts.official_sources_v50 import CAT_INTEGRATION
        if context.get('regional_report_scope')=='CATALONIA' and row.get('official_url')==CAT_INTEGRATION[2]:
            return ('PROCEDURAL_GUIDANCE',[context['routes'][0]['route_id']],
                    'Guía autonómica solo para el informe de integración en Cataluña; no sustituye los requisitos estatales ni certifica vigencia.')
        return 'UNRELATED', [], 'Guía autonómica fuera de su ámbito territorial o procedimiento'
    if source in ('migraciones', 'policia', 'boe'):
        return ('PROCEDURAL_GUIDANCE' if source == 'migraciones' else 'UNDETERMINED',
                [context['routes'][0]['route_id']] if source == 'migraciones' else [],
                'Pendiente de verificar correspondencia exacta con el procedimiento')
    return 'UNDETERMINED', [], 'Sin relación normativa específica acreditada'


def build_dossier(plan, evidence):
    context = procedure_context(plan)
    annotated = []
    buckets = {k: [] for k in APPLICABILITY}
    origin_by_provision = {'DA20.10': 'DA20_ARRAIGO_SOCIAL',
                           'DA21.10': 'DA21_ARRAIGO_EXTRAORDINARIO'}
    for row in evidence:
        result = _role(row, context)
        if len(result) == 4:
            role, routes, reason, specific_origin = result
        else:
            role, routes, reason = result
            specific_origin = origin_by_provision.get(str(row.get('article') or ''))
        assert role in APPLICABILITY
        eid = row['evidence_id']
        if specific_origin:
            origin = specific_origin
        elif context['business_category'] == 'regularizacion_2026':
            origin = ['DA20_ARRAIGO_SOCIAL', 'DA21_ARRAIGO_EXTRAORDINARIO']
        else:
            origin = context['origin_authorization']
        if role == 'CONDITIONALLY_APPLICABLE':
            verification = 'CONDITIONAL_RULE_MAPPED_INDIVIDUAL_ELIGIBILITY_NOT_ASSESSED'
        elif role == 'PROCEDURAL_GUIDANCE':
            verification = 'PROCEDURAL_SCOPE_MAPPED_ELIGIBILITY_NOT_ASSESSED'
        elif role == 'CONTEXT_ONLY':
            verification = 'CONTEXT_ONLY_NOT_USED_AS_ROUTE_REQUIREMENT'
        else:
            verification = 'UNVERIFIED_APPLICABILITY'
        cross_reference_role = {
            '74': 'REQUIREMENT_CONTENT_FOR_ART191_2_AJENA_LT_1Y',
            '80': 'REQUIREMENT_CONTENT_FOR_ART191_3_AJENA_GE_1Y',
            '86': 'REQUIREMENT_CONTENT_FOR_ART191_3_PROPIA_GE_1Y',
            '84': 'CONTEXT_FOR_ART191_4_ORIGIN_NOT_WORK_ENABLED',
        }.get(str(row.get('article') or ''))
        tagged = {
            'evidence_id': eid,
            'article_191_cross_reference_role': cross_reference_role,
            'source_url': row.get('official_url'),
            'issuing_authority': row.get('authority'),
            'source_type': 'LEGISLATION' if row.get('authority') == 'boe' else 'OFFICIAL_GUIDANCE',
            'legal_reference': row.get('legal_reference') or {
                'document': row.get('source_id'), 'article': row.get('article')},
            'legal_version': row.get('version_date'),
            'retrieved_at': row.get('retrieved_at'),
            'business_category': context['business_category'],
            'legal_regime': context['legal_regime'],
            'origin_authorization': origin,
            'destination_authorization': routes,
            'procedure_type': ('MULTIPLE_CONDITIONAL_ROUTES' if len(routes) > 1 else
                               'MODIFICACION' if routes and routes[0].startswith('MOD_') else
                               'PRORROGA' if routes and 'PRORROGA' in routes[0] else context['procedure_type']),
            'procedure_stage': ('INITIAL_APPLICATION' if plan.get('material_search_focus')=='INITIAL_SOCIAL_ARRAIGO' else 'POST_GRANT_CONTINUITY'),
            'applicability': role,
            'applicability_conditions': [reason],
            'supported_claims': [],
            'limitations': [reason],
            'verification_status': verification,
        }
        annotated.append(tagged)
        buckets[role].append(eid)
    return {
        'schema_version': '1.1',
        'procedure_context': context,
        'applicability_evidence': annotated,
        'buckets': buckets,
        'legal_accuracy_certified': False,
        'publication_allowed': False,
    }


def question_matrix(plan, evidence, coverage_questions, dossier):
    by_id = {row['evidence_id']: row for row in dossier['applicability_evidence']}
    context = dossier.get('procedure_context', {})
    answer = []
    for q in coverage_questions:
        relations = []
        conflicts = []
        for eid in q.get('evidence_ids') or []:
            record = by_id.get(eid)
            if not record:
                conflicts.append('UNKNOWN_EVIDENCE_ID:' + str(eid))
                continue
            relations.append({'evidence_id': eid, 'applicability': record['applicability'],
                              'route_ids': record['destination_authorization'],
                              'limitations': record['limitations']})
            if record['applicability'] in ('UNRELATED', 'UNDETERMINED'):
                conflicts.append('EVIDENCE_APPLICABILITY_NOT_ESTABLISHED:' + eid)
        answer.append({
            'question_id': q['id'], 'status': q.get('status'),
            'claim_text': q.get('question'), 'evidence_relations': relations,
            'missing_facts': q.get('missing_facts', []),
            'individual_case_variables': q.get('individual_case_variables', []),
            'non_blocking_unverified_details': q.get('non_blocking_unverified_details', []),
            'blocking_missing_facts': q.get('blocking_missing_facts', q.get('missing_facts', [])),
            'draft_readiness': q.get('draft_readiness', 'NOT_ASSESSED'),
            'applicability_conflicts': conflicts,
            'next_research_action': ('Resolve blocking legal facts' if q.get('blocking_missing_facts', q.get('missing_facts')) or conflicts
                                     else 'Draft only with explicit conditional branches and limitations; independent review required'),
        })
    return {'schema_version': '1.1', 'questions': answer,
            'publication_allowed': False, 'legal_accuracy_certified': False}


def scope_conflicts(question_matrix_obj):
    return [f"{x['question_id']}: {c}" for x in question_matrix_obj.get('questions', [])
            for c in x['applicability_conflicts']]


def audit_declared_claims(article, dossier):
    """Context-only material cannot substantiate a material legal claim by itself."""
    by_id = {r['evidence_id']: r for r in dossier.get('applicability_evidence', [])}
    rows = []
    errors = []
    for i, claim in enumerate(article.get('claims') or [], 1):
        if not isinstance(claim, dict):
            errors.append(f'Claim {i}: invalid claim object')
            continue
        ids = claim.get('evidence_ids') or []
        roles = [by_id[eid]['applicability'] for eid in ids if eid in by_id]
        valid = (len(roles) == len(ids) and bool(roles) and
                 any(r in ('DIRECTLY_APPLICABLE', 'CONDITIONALLY_APPLICABLE', 'PROCEDURAL_GUIDANCE') for r in roles))
        # A requirement reached via Article 191 cannot stand on the referred
        # provision alone in an extraordinary-regularisation continuity claim.
        # Its governing route must be cited, not merely assumed by the writer.
        if dossier.get('procedure_context', {}).get('business_category') == 'regularizacion_2026':
            refs=[by_id[eid].get('legal_reference') or {} for eid in ids if eid in by_id]
            nums={str(x.get('article')) for x in refs if x.get('document')==RD1155}
            if nums & {'74','80','86'} and '191' not in nums:
                valid=False
        rows.append({'claim_index': i - 1, 'claim': claim.get('claim'),
                     'evidence_ids': ids, 'applicability_roles': roles,
                     'requires_independent_review': True, 'context_only_or_unknown': not valid})
        if not valid:
            errors.append(f'Claim {i}: evidence is contextual, unknown or unrelated to target procedure')
    return {'claims': rows, 'legal_accuracy_certified': False}, errors


def general_guidance_branch_coverage(evidence, dossier):
    """Check that the general guide has the source material for its legal decision tree."""
    context = dossier.get('procedure_context', {})
    if context.get('business_category') != 'regularizacion_2026' or context.get('editorial_scope') != 'GENERAL_GUIDANCE':
        return {'applicable': False, 'ready': False, 'missing': ['Not a regularisation general guide']}
    rows = {(str(r.get('source_id') or ''), str(r.get('article') or '')): r for r in evidence}
    required = [(RD1155, '191'), (RD1155, '74'), (RD1155, '80'), (RD1155, '86'),
                (RD316, 'DA20.10'), (RD316, 'DA21.10')]
    missing = [f'{doc}:{article}' for doc, article in required if (doc, article) not in rows]
    article191 = rows.get((RD1155, '191'), {}).get('text', '').lower()
    checks191 = {
        '191.2 cuenta ajena / artículo 74': ('artículo 74' in article191 and 'cuenta ajena' in article191 and 'no lleve residiendo al menos un año' in article191),
        '191.3 cuenta ajena / artículo 80': ('artículo 80' in article191 and 'al menos un año' in article191 and 'ya habilitaba a trabajar' in article191),
        '191.3 cuenta propia / artículo 86': ('artículo 86' in article191 and 'al menos un año' in article191 and 'ya habilitaba a trabajar' in article191),
        '191.4 autorización de origen sin trabajo / artículo 84': ('artículo 84' in article191 and 'no habilitaba a trabajar' in article191),
    }
    missing.extend(name for name, ok in checks191.items() if not ok)
    exceptional_rules_ok = True
    for provision in ('DA20.10', 'DA21.10'):
        body = rows.get((RD316, provision), {}).get('text', '').lower()
        required_phrases = ('artículo 191', 'cuenta ajena', 'cuenta propia',
                            'prorrogará la validez', 'excepcionalmente',
                            'búsqueda activa de empleo', 'servicio público de empleo',
                            'informe de esfuerzo de integración', 'vigencia de un año',
                            'duración de cuatro años', 'edad legal de jubilación')
        absent = [phrase for phrase in required_phrases if phrase not in body]
        if absent:
            exceptional_rules_ok = False
            missing.append(provision + ': missing ' + ', '.join(absent))
    # A complete list of every possible document and an exclusive filing channel
    # are not prerequisites for a general explainer when the article labels them
    # unverified and makes no unsupported assertion about them.
    route_ids = {r['route_id'] for r in context.get('routes', [])}
    for branch in ARTICLE_191_BRANCHES:
        if branch['route_id'] not in route_ids:
            missing.append('route mapping missing: ' + branch['route_id'])
    if 'MOD_ART191_4_ORIGIN_NO_WORK' not in route_ids:
        missing.append('route mapping missing: MOD_ART191_4_ORIGIN_NO_WORK')
    return {'applicable': True, 'ready': not missing, 'missing': missing,
            'exceptional_extension_conditions_verified': exceptional_rules_ok and not any(x.startswith('DA20.10:') or x.startswith('DA21.10:') for x in missing),
            'required_evidence': [f'{doc}:{article}' for doc, article in required],
            'decision_variables': context.get('decision_variables', []),
            'unresolved_legal_branches': context.get('unresolved_legal_branches', [])}
