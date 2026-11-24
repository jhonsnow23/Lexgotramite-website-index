"""Supplemental official procedural evidence. Never certifies legal applicability.

Only pre-vetted entry points are fetched. Discovery is conservative; unknown topics
remain blocked rather than relying on a search-engine snippet or an old blog.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
from hashlib import sha256
from io import BytesIO
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
import re
import ssl

HOSTS = frozenset({
    'www.boe.es', 'boe.es',
    'www.inclusion.gob.es', 'inclusion.gob.es', 'sede.administracionespublicas.gob.es',
    'sede.policia.gob.es', 'www.mjusticia.gob.es', 'sede.mjusticia.gob.es',
})

# Official entry points verified for their subject; not authoritative for every query.
SOURCES = {
 'long_term_national': [
  ('migraciones','Hoja 49 — larga duración nacional',
   'https://www.inclusion.gob.es/web/migraciones/w/49.-autorizacion-de-residencia-de-larga-duracion-nacional'),
  ('policia','Tarjeta de residencia de larga duración',
   'https://sede.policia.gob.es/portalCiudadano/_es/tramites_extranjeria_tramite_tarjetaresidencia_largaduracion.php'),
  ('administraciones','MERCURIO — solicitud electrónica',
   'https://sede.administracionespublicas.gob.es/pagina/index/directorio/mercurio2/language/es_ES'),
 ],
 'long_term_eu': [
  ('migraciones','Hoja 50 — larga duración UE',
   'https://www.inclusion.gob.es/web/migraciones/w/50.-autorizacion-de-residencia-de-larga-duracion-ue'),
  ('policia','Tarjeta de residencia de larga duración',
   'https://sede.policia.gob.es/portalCiudadano/_es/tramites_extranjeria_tramite_tarjetaresidencia_largaduracion.php'),
 ],
 'nationality': [
  ('justicia','Nacionalidad por residencia',
   'https://sede.mjusticia.gob.es/tramites/nacionalidad-espanola'),
 ],
 'regularizacion_2026': [
  ('boe','Real Decreto 316/2026 — texto oficial publicado',
   'https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8284'),
  ('migraciones','Ministerio: preguntas sobre modificación o prórroga tras la regularización',
   'https://inclusion.gob.es/documents/20121/7817425/Preguntas%20y%20respuestas%2021072026.pdf/95dc64f0-7af9-a350-fc0e-b598dc0b9694?version=1.0'),
  ('migraciones','Ministerio: 100 preguntas técnicas de regularización',
   'https://inclusion.gob.es/documents/20121/7817425/100%20Preguntas%20t%C3%A9cnicas%20sobre%20regularizaci%C3%B3n.pdf/45bc4075-03f8-d568-6f19-440de6e701b7?download=true&version=1.0'),
  ('migraciones','Hoja 28 Ter — arraigo extraordinario',
   'https://www.inclusion.gob.es/web/migraciones/w/28-ter.-autorizacion-de-residencia-por-circunstancias-excepcionales-por-razon-de-arraigo-extraordinario'),
 ],
 'arraigo_temporal': [
  ('migraciones','Hoja 29 — arraigo sociolaboral',
   'https://www.inclusion.gob.es/es/web/migraciones/w/29.-autorizacion-de-residencia-temporal-por-circunstancias-excepcionales.-arraigo-sociolaboral.'),
  ('migraciones','Hoja 28 — arraigo social',
   'https://www.inclusion.gob.es/es/web/migraciones/w/autorizacion-residencia-temporal-por-circunstancias-excepcionales.-arraigo-social'),
 ],
 'cuenta_ajena': [
  ('migraciones','Migraciones: procedimientos de trabajo',
   'https://www.inclusion.gob.es/web/migraciones/w/renovacion-de-la-autorizacion-de-residencia-temporal-y-trabajo-por-cuenta-ajena'),
  ('administraciones','MERCURIO',
   'https://sede.administracionespublicas.gob.es/pagina/index/directorio/mercurio2/language/es_ES'),
 ],
 'cuenta_propia': [
  ('migraciones','Hoja 15 — renovación por cuenta propia',
   'https://www.inclusion.gob.es/web/migraciones/w/15.-renovacion-de-la-autorizacion-de-residencia-temporal-y-trabajo-por-cuenta-propia'),
 ],
 'no_lucrativa': [
  ('migraciones','Hoja 7 — renovación no lucrativa',
   'https://www.inclusion.gob.es/web/migraciones/w/renovacion-de-la-autorizacion-de-residencia-temporal-no-lucrativa'),
 ],
 'menores_no_nacidos': [
  ('migraciones','Hoja 42 — menores acompañados no nacidos en España',
   'https://www.inclusion.gob.es/web/migraciones/residencia'),
 ],
 'electronic_filing': [
  ('administraciones','MERCURIO',
   'https://sede.administracionespublicas.gob.es/pagina/index/directorio/mercurio2/language/es_ES'),
 ],
}


def subject(topic, group):
    t = str(topic).lower()
    try:
        from temporary_residence_policy_v50 import classify
    except ImportError:
        from scripts.temporary_residence_policy_v50 import classify
    commercial=classify(topic)
    if not commercial['excluded']:
        key=commercial['business_category']
        return 'arraigo_temporal' if key=='arraigo' else key
    if group == 'nationality': return 'nationality'
    if 'larga duraci' in t and (bool(re.search(r'\bue\b',t)) or 'unión europea' in t): return 'long_term_eu'
    if group in ('renewal','residence') and ('permanente' in t or 'larga duraci' in t):
        return 'long_term_national'  # candidate only; EU-family ambiguity remains unresolved
    return None


def candidates(topic, group):
    key=subject(topic,group)
    return list(SOURCES.get(key, []))


def allowed(url):
    try:
        p=urlparse(url)
        return p.scheme=='https' and p.hostname in HOSTS and not p.username and not p.password and (p.port in (None,443))
    except ValueError:
        return False


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,hdrs,newurl):
        if not allowed(newurl): raise ValueError('Redirect outside official allowlist')
        return super().redirect_request(req,fp,code,msg,hdrs,newurl)


class OfficialHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth=0; self.parts=[]; self.title=''; self.in_title=False
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg'): self.depth+=1
        if tag=='title':self.in_title=True
        if tag in ('p','li','h1','h2','h3','h4','tr','br'): self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg'):self.depth=max(0,self.depth-1)
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.depth:return
        if self.in_title:self.title+=data
        else:self.parts.append(data)
    def content(self):
        s=' '.join(''.join(self.parts).split())
        return s


def excerpt_for_legal_publication(body, limit=18000):
    """Retain the actual official legal passages relevant to regularisation.

    Fixed-size prefix truncation often loses the later additional provisions.
    Returned excerpts remain UNVERIFIED and require claim-level review.
    """
    needles = (r'disposici[oó]n adicional vig[eé]sima',
               r'disposici[oó]n adicional vig[eé]sima primera',
               r'art[ií]culo 191', r'pr[oó]rroga', r'modificaci[oó]n',
               r'regularizaci[oó]n extraordinaria')
    windows = []
    for pattern in needles:
        for match in list(re.finditer(pattern, body, flags=re.I))[:5]:
            begin = max(0, match.start()-350)
            end = min(len(body),match.end()+2200)
            if not any(begin >= a and end <= b for a,b in windows):
                windows.append((begin,end))
    # Priority order matters: additional provisions must not be crowded out
    # by earlier, repeated generic references to modifications.
    chunks=[];size=0
    for begin,end in windows:
        segment=body[begin:end]
        if size+len(segment)>limit:
            segment=segment[:max(0,limit-size)]
        if segment:chunks.append(segment);size+=len(segment)
        if size >= limit:break
    return '\n[...]\n'.join(chunks) if chunks else body[:limit]


def is_pdf_url(url):
    """Government document endpoints may end with an opaque UUID after .pdf."""
    return '.pdf' in urlparse(url).path.lower()


def extract_pdf_text(payload):
    """Parse a bounded official PDF, never OCR or trust its text as instructions."""
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(payload), strict=False)
    if reader.is_encrypted:
        raise ValueError('Encrypted official PDF')
    if len(reader.pages) > 160:
        raise ValueError('Official PDF too many pages')
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or '')
        if sum(map(len, parts)) > 650_000:
            raise ValueError('Official PDF extracted text too large')
    return '\n'.join(parts)


def excerpt_for_procedure_guidance(body, limit=18000):
    """Select post-grant continuity passages, including letter-spaced PDF text.

    PDFs from the ministry can spell text as 'm o d i f i c a c i ó n'.
    Search a whitespace-normalized parallel view while preserving original text
    and source offsets. Never reinterpret source text as certified legal facts.
    """
    compact = []
    offsets = []
    for i, char in enumerate(body):
        if not char.isspace():
            compact.append(char.lower())
            offsets.append(i)
    searchable = ''.join(compact)
    needles = (
        'modificaciónoprórroga', 'modificacionoprorroga',
        'modificacióndelaautorización', 'modificaciondelaautorizacion',
        'autoritzacióndelaresidencia',
        'artículo191', 'articulo191', 'norenovable', 'nosepuederenovar',
        'finalicelavigencia', 'expiracióndelaautorización',
    )
    matches = []
    for needle in needles:
        start = 0
        while len(matches) < 45:
            idx = searchable.find(needle, start)
            if idx < 0: break
            matches.append((idx, offsets[idx]))
            start = idx + len(needle)
    matches.sort(key=lambda pair: pair[0])
    # Do not fall back to the first 18k of a document concerning initial filing:
    # that would falsely imply sufficient evidence for a post-grant procedure.
    if not matches:
        return body[:min(limit, 1200)]
    windows = []
    for _, pos in matches:
        lo, hi = max(0, pos-500), min(len(body), pos+2200)
        if windows and lo <= windows[-1][1]:
            windows[-1] = (windows[-1][0], max(hi, windows[-1][1]))
        else:
            windows.append((lo, hi))
    excerpts = []
    remaining = limit
    for lo, hi in windows:
        segment = body[lo:hi][:remaining]
        if segment:
            excerpts.append(segment)
            remaining -= len(segment)
        if remaining <= 0: break
    return '\n[...]\n'.join(excerpts)


def retrieve_one(authority,title,url,*,fetch=None):
    if not allowed(url): raise ValueError('Non-allowlisted official URL')
    pdf = is_pdf_url(url)
    if fetch is None:
        opener=build_opener(SafeRedirect())
        def fetch(endpoint):
            req=Request(endpoint,headers={'User-Agent':'LexGoTramite-v50/official-research',
                'Accept':'application/pdf' if pdf else 'text/html','Accept-Language':'es'})
            with opener.open(req,timeout=20) as response:
                if not allowed(response.url): raise ValueError('Final URL outside allowlist')
                ctype=response.headers.get('Content-Type','').lower()
                expected='application/pdf' if pdf else 'text/html'
                if expected not in ctype: raise ValueError('Unexpected official content type: '+ctype[:80])
                max_bytes = 15_000_000 if pdf else 750_000
                payload=response.read(max_bytes+1)
                if len(payload)>max_bytes: raise ValueError('Official document exceeds maximum size')
                if pdf: return payload
                charset=response.headers.get_content_charset() or 'utf-8'
                return payload.decode(charset,errors='replace')
    raw=fetch(url)
    if pdf:
        if not isinstance(raw, bytes) or not raw.startswith(b'%PDF'):
            raise ValueError('Expected PDF bytes from official document')
        body=extract_pdf_text(raw)
        excerpt=excerpt_for_procedure_guidance(body)
    else:
        if not isinstance(raw,str):raise ValueError('Fetched content is not decoded HTML')
        parser=OfficialHTML();parser.feed(raw)
        body=parser.content()
        excerpt=excerpt_for_legal_publication(body) if authority=='boe' else body[:18000]
    if len(body)<150:raise ValueError('Official source had insufficient extracted text')
    digest=sha256(body.encode('utf-8')).hexdigest()
    stamp=datetime.now(timezone.utc).isoformat()
    legal_publication = authority == 'boe'
    return {'evidence_id':'EV_'+digest[:20].upper(), 'source_id':authority,
      'authority':authority,'document_title':title,'article':None,
      'official_url':url,'api_url':None,'retrieved_at':stamp,
      'version_date':None,'version_status':'GUIDANCE_DATE_NOT_VERIFIED',
      'legal_status':'OFFICIAL_LEGAL_TEXT_UNVERIFIED' if legal_publication else 'PROCEDURAL_GUIDANCE_UNVERIFIED',
      'text':excerpt, 'sha256':digest,
      'research_relevance':{'semantic_verification_required':True,
       'source_type':'official_legal_publication' if legal_publication else 'official_procedural_guidance'}}


def retrieve_for_topic(topic,group,*,fetch=None):
    records=[];errors=[];attempts=[]
    for authority,title,url in candidates(topic,group):
        try:
            rec=retrieve_one(authority,title,url,fetch=fetch)
            records.append(rec)
            attempts.append({'source':authority,'url':url,'status':'RETRIEVED_UNVERIFIED'})
        except Exception as e:
            errors.append({'category':'OFFICIAL_SOURCE_RETRIEVAL_ERROR',
              'source':authority,'url':url,'details':type(e).__name__+': '+str(e)[:200]})
            attempts.append({'source':authority,'url':url,'status':'ERROR'})
    return records,errors,attempts
