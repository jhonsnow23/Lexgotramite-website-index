#!/usr/bin/env python3
"""Commercial scope gate for v5.0. Classifies TOPICS, never certifies legal rules."""
import re
import unicodedata

CATEGORIES = (
    ('regularizacion_2026', 1, 'Cómo continuar la residencia tras la regularización extraordinaria de 2026', 'regularizacion extraordinaria 2026 modificacion residencia'),
    ('arraigo', 2, 'Prórroga o modificación de residencia por arraigo sociolaboral', 'renovar arraigo sociolaboral'),
    ('cuenta_ajena', 3, 'Renovación de residencia y trabajo por cuenta ajena al cambiar de empleador', 'renovar permiso trabajo cuenta ajena'),
    ('cuenta_propia', 4, 'Renovación de residencia y trabajo por cuenta propia para autónomos', 'renovar residencia autonomo cuenta propia'),
    ('no_lucrativa', 5, 'Renovación de residencia temporal no lucrativa', 'renovacion residencia no lucrativa'),
    ('menores_no_nacidos', 6, 'Renovación de residencia de hijo menor no nacido en España', 'renovar residencia hijo menor no nacido espana'),
)
SEEDS = {key:{'business_category':key,'priority':rank,'proposed_title':title,'primary_query':query} for key,rank,title,query in CATEGORIES}


def norm(s):
    s=''.join(c for c in unicodedata.normalize('NFKD',str(s).lower()) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+',s))


def classify(topic, queries=(), cluster=''):
    """Fail closed for ambiguity. Queries provide hints, not proof of a legal route."""
    title=norm(topic)
    # Recognize the granted authorization as a synonym only in an explicit
    # post-grant continuity title, not in initial application or card topics.
    synonym_pattern = r'\bautorizacion extraordinaria(?: de residencia(?: y trabajo)?)?(?: concedida| obtenida)? (?:de |en )?2026\b'
    synonym = bool(re.search(synonym_pattern, title))
    continuation = bool(re.search(r'\b(continuidad|continuar|modificacion|modificar|prorroga|prorrogar|renovacion|renovar)\b', title))
    post_grant = bool(re.search(r'\b(tras|despues de|titulares de|concedida|obtenida)\b', title))
    initial_or_card = bool(re.search(r'\b(como solicitar|solicitud inicial|solicitar (?:la )?autorizacion extraordinaria|solicitud de (?:la )?autorizacion extraordinaria|requisitos para solicitar|estado expediente|estado de solicitud|cuanto tarda|tiempo de tramitacion|tie|nie|tarjeta|huellas)\b', title))
    # Modification and extension operate on an existing authorization; unlike
    # generic renewal wording, they do not need a separate post-grant marker.
    explicit_existing_procedure = bool(re.search(r'\b(modificacion|modificar|prorroga|prorrogar)\b', title))
    if synonym and continuation and (post_grant or explicit_existing_procedure) and not initial_or_card:
        title = re.sub(synonym_pattern, 'regularizacion extraordinaria de 2026', title)
    elif synonym and initial_or_card:
        return {'business_category':None,'search_intent':topic,'legal_procedure':None,
                'procedure_type':None,'applicable_regulation':[], 'target_audience':None,
                'priority':None,'excluded':True,'exclusion_reason':'INITIAL_OR_CARD_EXTRAORDINARY_AUTHORIZATION'}
    qs=' '.join(norm(q) for q in queries if q)
    cluster=norm(cluster)
    text=' '.join((title,qs,cluster))
    result={'business_category':None,'search_intent':topic,'legal_procedure':None,
      'procedure_type':None,'applicable_regulation':[], 'target_audience':None,
      'priority':None,'excluded':True,'exclusion_reason':None}
    forbidden=('larga duracion','residencia permanente','tarjeta permanente','nacionalidad',
      'toma huellas','cita huellas','duplicado tie','robo tie','perdida tie',
      'renovacion nie','expedicion tie','tarjeta identidad extranjero')
    # A query about applying for the extraordinary regularisation is NOT a
    # request to continue an authorization already granted. Never reframe it.
    initial_processing = (
        'regularizacion' in title and
        any(term in title for term in (
            'cuanto tarda', 'cuanto tiempo tarda', 'tiempo de tramitacion',
            'estado expediente', 'estado de solicitud', 'consultar expediente',
            'cuando sale', 'cuando me aprueban', 'como solicitar',
            'solicitar regularizacion', 'requisitos para solicitar',
        )) and
        not any(term in title for term in (
            'despues de obtener', 'tras obtener', 'autorizacion concedida',
            'permiso concedido', 'cuando vence', 'tras la regularizacion',
        ))
    )
    if initial_processing:
        result['exclusion_reason']='INITIAL_REGULARIZATION_PROCESSING_NOT_TEMPORARY_RENEWAL';return result
    if any(x in text for x in forbidden):
        result['exclusion_reason']='EXCLUDED_PERMANENT_CARD_OR_OTHER_PROCEDURE';return result
    if re.search(r'\b(tie|nie)\b',text) and not any(x in text for x in ('autorizacion temporal','cuenta ajena','arraigo','regularizacion','menor no nacido')):
        result['exclusion_reason']='DOCUMENT_CARD_ONLY';return result
    matches=[]
    if ('regularizacion' in text and any(x in text for x in ('extraordinaria','masiva','2026','regularizacion 2026'))) or ('arraigo extraordinario' in text and '2026' in text):
        matches.append('regularizacion_2026')
    if 'arraigo' in text and 'extraordinario' not in text:matches.append('arraigo')
    if ('cuenta ajena' in text or 'empleador' in text or 'contrato trabajo' in text) and 'regularizacion' not in text:matches.append('cuenta_ajena')
    if ('cuenta propia' in text or 'autonomo' in text or 'autonomos' in text) and 'regularizacion' not in text:matches.append('cuenta_propia')
    if 'no lucrativa' in text:matches.append('no_lucrativa')
    if ('menor' in text or 'hijo' in text or 'hija' in text) and ('no nacido' in text or 'no nacida' in text or 'fuera de espana' in text):matches.append('menores_no_nacidos')
    matches=list(dict.fromkeys(matches))
    if len(matches)!=1:
        result['exclusion_reason']='AMBIGUOUS_OR_OUT_OF_SCOPE' if not matches else 'MULTIPLE_PROCEDURES_REQUIRE_RESEARCH'
        return result
    category=matches[0]
    if any(w in title for w in ('prorroga','prorrogar')):kind='PRORROGA'
    elif any(w in title for w in ('modificacion','modificar','cambiar autorizacion')):kind='MODIFICACION'
    elif category=='regularizacion_2026':kind=None  # Needs authoritative determination
    elif category=='arraigo':kind=None  # Routes differ by modality and transitional law
    else:kind='RENOVACION'
    if category in ('regularizacion_2026','arraigo') and any(x in title for x in ('renovar','renovacion')):kind=None
    # A comparison of two ordinary arraigo continuity mechanisms is not itself
    # a choice of procedure. Keep the classification pending until researched.
    if category=='arraigo' and any(w in title for w in ('prorroga','prorrogar')) and any(w in title for w in ('modificacion','modificar')):kind=None
    result.update(business_category=category,priority=SEEDS[category]['priority'],excluded=False,
        exclusion_reason=None,procedure_type=kind,legal_procedure='PENDING_OFFICIAL_CLASSIFICATION' if kind is None else kind,
        applicable_regulation=['RD 1155/2024 (texto consolidado)','RD 316/2026 (verificar aplicabilidad)'],
        target_audience={
          'regularizacion_2026':'Titulares de autorización extraordinaria de 2026',
          'arraigo':'Titulares de autorización temporal por arraigo',
          'cuenta_ajena':'Trabajadores extranjeros por cuenta ajena',
          'cuenta_propia':'Trabajadores extranjeros autónomos',
          'no_lucrativa':'Residentes temporales sin actividad lucrativa',
          'menores_no_nacidos':'Familias de menores acompañados no nacidos en España',
        }[category])
    return result


def research_questions(category):
    # A general post-regularisation explainer is not an individual application.
    # Evaluate the decision tree and its conditions, not an imaginary universal
    # document checklist spanning all possible modifications under Article 191.
    if category == 'regularizacion_2026':
        return [
            {'id':'scope',
             'question':'Qué opciones generales de continuidad prevé la normativa para quien YA tiene la autorización extraordinaria de 2026, distinguiendo modificación del artículo 191, prórroga excepcional y supuestos a los que se aplican',
             'query':'autorización extraordinaria 2026 ya concedida modificación artículo 191 prórroga excepcional'},
            {'id':'requirements',
             'question':'Qué condiciones determinan la vía de modificación por cuenta ajena o propia según el artículo 191, y qué condiciones oficiales habilitan la prórroga excepcional; diferenciar reglas de cada vía sin inventar una lista universal de documentos',
             'query':'regularización extraordinaria continuidad artículo 191 requisitos según vía modificación prórroga excepcional'},
            {'id':'steps',
             'question':'Qué plazos y efectos de la continuidad tras la autorización extraordinaria de 2026 están expresamente documentados, y qué pasos de presentación están acreditados; identificar como NO VERIFICADOS los canales o documentos no descritos',
             'query':'regularización extraordinaria 2026 modificación prórroga plazo presentar procedimiento artículo 191'},
        ]
    name={
      'regularizacion_2026':'continuidad de la autorización extraordinaria de 2026: modificación del artículo 191 o posible prórroga',
      'arraigo':'continuidad de la modalidad específica de arraigo: prórroga o modificación y disposiciones transitorias',
      'cuenta_ajena':'renovación de autorización temporal de residencia y trabajo por cuenta ajena',
      'cuenta_propia':'renovación de autorización temporal de residencia y trabajo por cuenta propia',
      'no_lucrativa':'renovación de autorización temporal de residencia no lucrativa',
      'menores_no_nacidos':'renovación de autorización de residencia de menor acompañado no nacido en España',
    }[category]
    return [
      {'id':'scope','question':f'Qué procedimiento corresponde realmente a {name} y a quién se aplica','query':name+' normativa vigente'},
      {'id':'requirements','question':f'Qué requisitos, documentos y excepciones se aplican específicamente a {name}','query':name+' requisitos documentos excepciones'},
      {'id':'steps','question':f'Qué plazos, vías de solicitud y efectos jurídicos están acreditados para {name}','query':name+' plazos presentación efectos'},
    ]


def employer_change_focus(category, topic):
    """Recognise the material search-intent qualifier, not a legal conclusion."""
    text = norm(topic)
    return category == 'cuenta_ajena' and bool(re.search(
        r"(?:cambi\w*|nuev\w*|otr[oa])\s+(?:de\s+)?(?:empleador|empresa)", text))

def employer_change_questions():
    return [
        {'id':'scope','question':'Qué supuestos de renovación por cuenta ajena al cambiar de empleador están acreditados, distinguiendo artículo 80.2.b.1.º y 2.º, su ámbito y las condiciones de cada uno, sin confundir renovación con un cambio durante la vigencia de la autorización inicial', 'query':'renovación residencia trabajo cuenta ajena cambio de empleador artículo 80 apartado 2 b nuevo contrato'},
        {'id':'requirements','question':'Qué requisitos, excepciones y documentos acreditativos se aplican al cambio de empleador en la renovación: periodo de actividad, nuevo contrato, alta o situación asimilada, inicio condicionado y remisión al artículo 74 cuando proceda; distinguir otros supuestos del artículo 80 de estos dos', 'query':'renovación cuenta ajena nuevo empleador artículo 80 74 requisitos documentación alta contrato condicionado'},
        {'id':'steps','question':'Qué plazos, presentación, efectos y consecuencias de la solicitud de renovación al cambiar de empleador están acreditados; distinguir los efectos generales y las condiciones específicas del nuevo contrato, y señalar cualquier detalle material no verificado', 'query':'renovación cuenta ajena cambio empleador artículo 80 plazo presentación efectos nuevo contrato documentación'},
    ]
