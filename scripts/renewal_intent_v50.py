"""Commercial intent gate; never infer legal applicability from a search query.
Imported Keyword Planner metrics are user-supplied estimates, not API-verified data.
"""
import csv
import io
import re
try:
    from . import temporary_residence_policy_v50 as policy
except ImportError:
    import temporary_residence_policy_v50 as policy

CONTINUITY = re.compile(r'\b(?:renov\w*|renuev\w*|prorrog\w*|modific\w*|continu\w*|caduc\w*|venc\w*|expir\w*)\b')
INITIAL = re.compile(r'\b(?:por primera vez|primera solicitud|solicitud inicial|acceso inicial|obtener por primera vez|conseguir por primera vez|primera autorizacion|solicitar (?:el |la |un |una )?(?:arraigo|regularizacion|residencia|permiso|autorizacion))\b')
CARD = re.compile(r'\b(?:tie|nie|huellas|duplicado|tarjeta|plastico)\b')
# Narrow questions, not legal conclusions or claims of keyword volume. Avoid
# repeating Run57's successful non-lucrative deadline article.
FALLBACKS = (
 ('no_lucrativa','Renovación de residencia no lucrativa: cuánto dura la autorización renovada'),
 ('cuenta_ajena','Primera renovación de residencia y trabajo por cuenta ajena: cuánto dura la autorización renovada'),
 ('cuenta_propia','Renovación de residencia y trabajo por cuenta propia: duración de la autorización renovada'),
 ('arraigo','Prórroga del arraigo sociolaboral: condiciones y límites'),
 ('menores_no_nacidos','Renovación de residencia de hijos menores no nacidos en España: duración de la autorización'),
 ('regularizacion_2026','Continuidad de residencia tras la regularización extraordinaria de 2026: opciones de modificación'),
)


def assess(query):
    text=policy.norm(query); c=policy.classify(query)
    if c['excluded']:return {**c,'renewal_intent_verified':False}
    # Reject ambiguous card requests, even if a category is mentioned. Card
    # expiry is not necessarily expiry of the underlying authorization.
    if CARD.search(text):reason='DOCUMENT_CARD_OR_AMBIGUOUS_CARD_INTENT'
    elif not CONTINUITY.search(text):reason='NO_EXPLICIT_EXISTING_AUTHORIZATION_CONTINUITY'
    elif INITIAL.search(text) and not re.search(r'\b(?:primera renovacion|renovar[^.]{0,80}por primera vez|solicitar (?:la |una )?renovacion|solicitar (?:la |una )?prorroga|solicitar (?:la |una )?modificacion)\b',text):reason='INITIAL_OR_MIXED_APPLICATION_INTENT'
    elif re.search(r'\b(?:estado (?:del |de )?expediente|consultar expediente|cita previa|cuanto tarda la resolucion)\b',text):reason='ADMINISTRATIVE_STATUS_OR_AMBIGUOUS_INTENT'
    else:reason=None
    return {**c,'excluded':bool(reason),'exclusion_reason':reason,'renewal_intent_verified':not bool(reason)}


def assess_group(title, queries=()):
    result=assess(title)
    if result['excluded']:return result
    for query in queries:
        q=assess(query)
        if q['excluded'] or q['business_category']!=result['business_category']:
            return {**result,'excluded':True,'renewal_intent_verified':False,'exclusion_reason':'MIXED_OR_UNVERIFIED_RENEWAL_QUERY_GROUP'}
    return result


def planner_rows(raw):
    """Explicitly imported normalized CSV, Spain / Spanish asserted by uploader.
    Exact columns avoid ambiguous decimal separators or unsupported ranges.
    No API access, no proof of authenticity, and no fabricated GSC impressions.
    """
    if not raw:return []
    if len(raw.encode('utf-8'))>48000:raise ValueError('Keyword Planner CSV exceeds 48 KB')
    reader=csv.DictReader(io.StringIO(raw.lstrip('\ufeff')))
    if set(reader.fieldnames or [])!={'keyword','avg_monthly_searches'}:
        raise ValueError('Keyword Planner CSV must have keyword,avg_monthly_searches columns')
    rows={}
    for r in reader:
        q=(r.get('keyword') or '').strip(); volume=(r.get('avg_monthly_searches') or '').strip()
        if not q or len(q)>220 or not re.fullmatch(r'[0-9]{1,9}',volume):raise ValueError('Invalid Keyword Planner CSV row; exact nonnegative integer required')
        c=assess(q)
        if c['excluded'] or int(volume)==0:continue
        key=policy.norm(q)
        if key in rows and rows[key]['avg_monthly_searches']!=int(volume):raise ValueError('Conflicting keyword estimates in import')
        rows[key]={'query':q,'category':c['business_category'],'avg_monthly_searches':int(volume),'origin':'KEYWORD_PLANNER_IMPORT','market':'Spain / Spanish (uploader-declared)','api_verified':False}
    return sorted(rows.values(),key=lambda r:(-r['avg_monthly_searches'],r['query']))
