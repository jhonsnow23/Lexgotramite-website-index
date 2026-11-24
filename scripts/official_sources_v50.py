"""Supplemental official procedural evidence. Never certifies legal applicability.

Only pre-vetted entry points are fetched. Discovery is conservative; unknown topics
remain blocked rather than relying on a search-engine snippet or an old blog.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
from hashlib import sha256
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
import re
import ssl

HOSTS = frozenset({
    'www.inclusion.gob.es', 'sede.administracionespublicas.gob.es',
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
  ('migraciones','Migraciones: regularización extraordinaria',
   'https://www.inclusion.gob.es/web/migraciones/residencia'),
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


def retrieve_one(authority,title,url,*,fetch=None):
    if not allowed(url): raise ValueError('Non-allowlisted official URL')
    if fetch is None:
        opener=build_opener(SafeRedirect())
        def fetch(endpoint):
            req=Request(endpoint,headers={'User-Agent':'LexGoTramite-v50/official-research',
                'Accept':'text/html','Accept-Language':'es'})
            with opener.open(req,timeout=15) as response:
                if not allowed(response.url):raise ValueError('Final URL outside allowlist')
                ctype=response.headers.get('Content-Type','')
                if 'text/html' not in ctype:raise ValueError('Unexpected content type')
                payload=response.read(750_001)
                if len(payload)>750_000:raise ValueError('Official page exceeds maximum size')
                charset=response.headers.get_content_charset() or 'utf-8'
                return payload.decode(charset,errors='replace')
    html=fetch(url)
    if not isinstance(html,str):raise ValueError('Fetched content is not decoded HTML')
    parser=OfficialHTML();parser.feed(html)
    body=parser.content()
    if len(body)<150:raise ValueError('Official source had insufficient extracted text')
    # This excerpt is a retrieval candidate, not proof of procedure or applicability.
    # Important: the whole source has a content fingerprint even when excerpt bounded.
    digest=sha256(body.encode('utf-8')).hexdigest()
    stamp=datetime.now(timezone.utc).isoformat()
    return {'evidence_id':'EV_'+digest[:20].upper(), 'source_id':authority,
      'authority':authority,'document_title':title,'article':None,
      'official_url':url,'api_url':None,'retrieved_at':stamp,
      'version_date':None,'version_status':'GUIDANCE_DATE_NOT_VERIFIED',
      'legal_status':'PROCEDURAL_GUIDANCE_UNVERIFIED',
      'text':body[:18000], 'sha256':digest,
      'research_relevance':{'semantic_verification_required':True,
       'source_type':'official_procedural_guidance'}}


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
