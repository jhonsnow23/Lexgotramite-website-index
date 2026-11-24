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
from urllib.error import URLError
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
  ('migraciones','Hoja 55 — modificación desde residencia temporal que habilita a trabajar',
   'https://www.inclusion.gob.es/documents/410169/2260168/55.%2BModificaci%C3%B3n%2Bdesde%2Bsituaciones%2Bde%2Bautorizaciones%2Bde%2Bresidencia%2Btemporal%2Bque%2Bhabilitan%2Ba%2Btrabajar.pdf/'),
  ('migraciones','Formulario EX-26 — solicitud de modificación de residencia o estancia',
   'https://inclusion.gob.es/documents/d/migraciones/ex26-formulario-de-solicitud-modificacion-de-autorizacion-de-residencia-o-estancia-editable-1'),
  ('migraciones','Criterio de gestión DGGMR 1/2025 — modificación y prórroga según artículo 191',
   'https://www.inclusion.gob.es/documents/d/migraciones/criterio-de-gestion-dggm_rloex-1-2025_modificaciones-estancias-y-residencias-y-prorrogas-arraigos'),
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


def extract_rd316_continuity_provisions(body, limit=18000):
    """Extract both operative paragraph-10 sections, never preamble matches."""
    anchors = (
        (r'(?<!\d)10\.\s+La autorizaci[oó]n concedida tendr[aá] una vigencia',
         r'(?<!\w)Doce\.\s+Se a[nñ]ade'),
        (r'(?<!\d)10\.\s+La autorizaci[oó]n de residencia temporal por '
         r'circunstancias excepcionales por raz[oó]n de arraigo extraordinario',
         r'(?<!\w)Trece\.\s+'),
    )
    sections = []
    for start_pattern, end_pattern in anchors:
        starts = list(re.finditer(start_pattern, body, flags=re.I))
        if not starts:
            return None
        start = starts[-1].start()
        ending = re.search(end_pattern, body[start:], flags=re.I)
        end = start + ending.start() if ending else min(len(body), start + 7000)
        segment = body[start:min(end, start + 7000)].strip()
        if not segment:
            return None
        sections.append(segment)
    joined = '\n[...]\n'.join(sections)
    # Do not silently clip operative regulations: fall back to existing extractor.
    return joined if len(joined) <= limit else None


def excerpt_for_legal_publication(body, limit=18000):
    """Retain the actual official legal passages relevant to regularisation.

    Fixed-size prefix truncation often loses the later additional provisions.
    Returned excerpts remain UNVERIFIED and require claim-level review.
    """
    operative = extract_rd316_continuity_provisions(body, limit=limit)
    if operative is not None:
        return operative
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


def normalize_letter_spaced_pdf_text(body):
    """Undo PDF glyph spacing without rewriting ordinary prose or legal content.

    Some official PDFs extract each letter separately (``m o d i f i c a``),
    while word gaps are two or more spaces. This is a presentation-only
    transformation; the normalized evidence remains marked unverified.
    """
    # Only activate for documents with pervasive individual-character spacing.
    runs = re.findall(r'(?<!\S)(?:[^\W\d_][ \t]){3,}[^\W\d_](?!\S)', body, flags=re.UNICODE)
    if len(runs) < 15:
        return body
    def fix_line(line):
        chunks = re.split(r'([ \t]{2,})', line)
        for i, chunk in enumerate(chunks):
            if re.fullmatch(r'[^\W\d_](?:[ \t][^\W\d_])+', chunk, flags=re.UNICODE):
                chunks[i] = re.sub(r'[ \t]', '', chunk)
            elif re.fullmatch(r'[0-9](?:[ \t][0-9])+', chunk):
                chunks[i] = re.sub(r'[ \t]', '', chunk)
            elif re.fullmatch(r'[0-9][ \t]+\.', chunk):
                chunks[i] = re.sub(r'[ \t]+', '', chunk)
        joined = ''.join(chunks)
        joined = re.sub(r'(?<!\w)(?:[^\W\d_][ \t]){2,}[^\W\d_](?!\w)',
                        lambda m: re.sub(r'[ \t]', '', m.group()), joined, flags=re.UNICODE)
        joined = re.sub(r'(?<!\d)[0-9](?:[ \t][0-9])+(?!\d)',
                        lambda m: re.sub(r'[ \t]', '', m.group()), joined)
        return re.sub(r'[ \t]{2,}', ' ', joined)
    return '\n'.join(fix_line(line) for line in body.split('\n'))


def excerpt_for_procedure_guidance(body, limit=18000):
    """Prioritize actual post-grant FAQ answers over a PDF table of contents.

    Ministry PDFs may mention questions 39-43 in the index and repeat them
    later with the answers. Select the final occurrence of the numbered
    *question* and retain its answer until the following question. Extracted
    text is still unverified: this is an evidence discovery step only.
    """
    def numbered_questions(text):
        # Anchors require a question mark, so page numbers or section lists
        # without actual questions do not masquerade as answer locations.
        return list(re.finditer(r'(?m)^\s*(\d{1,3})\s*\.\s*¿', text))

    questions = numbered_questions(body)
    anchors = {}
    for i, match in enumerate(questions):
        number = int(match.group(1))
        if number not in (39, 40, 41, 42, 43, 48, 49):
            continue
        end = questions[i + 1].start() if i + 1 < len(questions) else min(len(body), match.start() + 5000)
        section = body[match.start():end]
        # A TOC line has a question title, but not its explanatory answer.
        # Prefer the latest substantial occurrence, even if the TOC includes
        # extra page-number annotations.
        if len(section.strip()) >= 35:
            anchors[number] = section[:3600]

    if anchors:
        selected = []
        remaining = limit
        for number in (39, 40, 41, 42, 43, 48, 49):
            section = anchors.get(number)
            if not section or remaining <= 0:
                continue
            selected.append(section[:remaining])
            remaining -= len(selected[-1])
        if selected:
            return '\n[...]\n'.join(selected)[:limit]

    # Other government PDFs may not use the numbered-FAQ format. Retain the
    # previous search, but prioritize the *last* instances of each phrase:
    # they are more likely to describe the answer rather than the TOC.
    compact, offsets = [], []
    for i, char in enumerate(body):
        if not char.isspace():
            compact.append(char.lower())
            offsets.append(i)
    searchable = ''.join(compact)
    needles = (
        'modificaciónoprórroga', 'modificacionoprorroga',
        'modificacióndelaautorización', 'modificaciondelaautorizacion',
        'artículo191', 'articulo191', 'norenovable', 'nosepuederenovar',
        'finalicelavigencia', 'expiracióndelaautorización',
    )
    positions = set()
    for needle in needles:
        start = 0
        while True:
            idx = searchable.find(needle, start)
            if idx < 0:
                break
            positions.add(offsets[idx])
            start = idx + len(needle)
    if not positions:
        return body[:min(limit, 1200)]
    # Discard the beginning when a longer document has matching later prose.
    priority = sorted(positions, reverse=True)
    windows = []
    for pos in priority:
        lo, hi = max(0, pos - 350), min(len(body), pos + 2400)
        if any(lo >= old_lo and hi <= old_hi for old_lo, old_hi in windows):
            continue
        windows.append((lo, hi))
        if len(windows) >= 8:
            break
    windows.sort()
    excerpts = []
    remaining = limit
    for lo, hi in windows:
        if remaining <= 0:
            break
        section = body[lo:hi][:remaining]
        excerpts.append(section)
        remaining -= len(section)
    return '\n[...]\n'.join(excerpts)[:limit]

def excerpt_for_article_191_criterion(body, limit=18000):
    """Prefer article 191.2/191.3 modification guidance over unrelated 191.8.

    Source-specific retrieval, NOT legal applicability certification. Excerpts
    retain document text unchanged; absence of a matching passage is reported
    through the normal evidence validation process.
    """
    patterns = (
        r'(?:art[ií]culo\s+)?191\s*\.\s*2\b',
        r'(?:art[ií]culo\s+)?191\s*\.\s*3\b',
        r'menos de un a[nñ]o',
        r'al menos un a[nñ]o',
    )
    windows = []
    for pattern in patterns:
        for match in list(re.finditer(pattern, body, flags=re.I))[:12]:
            lo, hi = max(0, match.start()-500), min(len(body), match.end()+1700)
            if not any(lo >= a and hi <= b for a,b in windows):
                windows.append((lo,hi))
    if not windows:
        return excerpt_for_procedure_guidance(body, limit=limit)
    selected, used = [], 0
    for lo,hi in sorted(windows):
        part = body[lo:hi][:max(0, limit-used)]
        if part:
            selected.append(part)
            used += len(part)
        if used >= limit:
            break
    return '\n[...]\n'.join(selected)[:limit]


def is_certificate_verification_error(error):
    """Distinguish broken certificate chains from ordinary HTTP/network failures."""
    reason = error.reason if isinstance(error, URLError) else error
    return isinstance(reason, ssl.SSLCertVerificationError)


def official_tls_alternative(url):
    """Retry the Ministry's other HTTPS hostname; never disable TLS checks.

    This is an availability fallback, not evidence of legal validity.
    Both domains remain subject to the same strict official-host allowlist.
    """
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'inclusion.gob.es' or not allowed(url):
        return None
    return urlunparse(parsed._replace(netloc='www.inclusion.gob.es'))


def retrieve_one(authority,title,url,*,fetch=None):
    if not allowed(url): raise ValueError('Non-allowlisted official URL')
    pdf = is_pdf_url(url) or urlparse(url).path.startswith('/documents/d/migraciones/')
    resolved_url = [url]
    if fetch is None:
        opener=build_opener(SafeRedirect())
        def fetch(endpoint):
            request_urls = [endpoint]
            alternative = official_tls_alternative(endpoint) if pdf else None
            if alternative:
                request_urls.append(alternative)
            for index, request_url in enumerate(request_urls):
                req=Request(request_url,headers={'User-Agent':'LexGoTramite-v50/official-research',
                    'Accept':'application/pdf' if pdf else 'text/html','Accept-Language':'es'})
                try:
                    with opener.open(req,timeout=20) as response:
                        if not allowed(response.url): raise ValueError('Final URL outside allowlist')
                        ctype=response.headers.get('Content-Type','').lower()
                        expected='application/pdf' if pdf else 'text/html'
                        if expected not in ctype: raise ValueError('Unexpected official content type: '+ctype[:80])
                        max_bytes = 15_000_000 if pdf else 750_000
                        payload=response.read(max_bytes+1)
                        if len(payload)>max_bytes: raise ValueError('Official document exceeds maximum size')
                        resolved_url[0] = response.url
                        if pdf: return payload
                        charset=response.headers.get_content_charset() or 'utf-8'
                        return payload.decode(charset,errors='replace')
                except URLError as error:
                    if index == 0 and alternative and is_certificate_verification_error(error):
                        continue
                    raise
    raw=fetch(url)
    if pdf:
        if not isinstance(raw, bytes) or not raw.startswith(b'%PDF'):
            raise ValueError('Expected PDF bytes from official document')
        raw_pdf_text=extract_pdf_text(raw)
        body=normalize_letter_spaced_pdf_text(raw_pdf_text)
        excerpt=(excerpt_for_article_191_criterion(body)
                 if 'criterio de gestión' in title.lower() and '191' in title
                 else excerpt_for_procedure_guidance(body))
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
      'official_url':url,'retrieval_url':resolved_url[0],'api_url':None,'retrieved_at':stamp,
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
