"""Deterministic editorial helpers. Never alter material legal facts or approve a draft."""
from html.parser import HTMLParser
from urllib.parse import urlsplit, parse_qs, unquote
from urllib.request import Request
from difflib import SequenceMatcher
import re
import unicodedata

RD='BOE-A-2024-24099'; LO='BOE-A-2000-544'
NAMES={RD:'Reglamento de Extranjería (RD 1155/2024)', LO:'Ley Orgánica 4/2000'}
WRITING = '''EDITORIAL: escribe para una persona sin conocimientos jurídicos, en español natural de España, de tú, con frases claras y consecuencias prácticas. Empieza con un párrafo introductorio específico y útil (section="Introducción" en el primer claim, con sus evidencias); no empieces con el nombre de la norma ni con advertencias genéricas. Responde pronto a la pregunta. Usa encabezados naturales, preferentemente preguntas del cliente. Cada párrafo debe aportar información nueva. text contiene la explicación principal; conditions y exceptions solo añaden condiciones y salvedades distintas que no estén ya explicadas en text ni en otro párrafo. conditions y exceptions pueden estar vacíos si no hay una condición o salvedad adicional que añadir; las condiciones y excepciones materiales deben figurar en algún campo del párrafo o en otro párrafo claramente aplicable. Explica términos como silencio administrativo y procedimiento sancionador en lenguaje cotidiano sin alterar su significado. Conserva todos los plazos, requisitos, excepciones y advertencias materiales. No confundas tarjeta física y autorización. No repitas la introducción en una conclusión o FAQ. No prometas una guía completa, no incluyas relleno ni mensajes de venta; Python añade una única invitación de contacto si está verificada. Las citas se renderizan desde el catálogo. Las limitaciones del lector deben ser concretas y aportar información distinta, sin ocultar incertidumbre. Solo en RESOLVED_BY_EVIDENCE, reader_limitation puede quedar vacío cuando no existe una limitación adicional para el lector: conserva el razonamiento y las citas; nunca omitas una advertencia material. No añadas un claim nuevo solo por alargar el texto.'''
REVIEW = '''EDITORIAL: revisa también si el texto responde en lenguaje natural a una persona que no conoce la ley, si la introducción se centra en su problema, si cada párrafo aporta valor, si las citas son comprensibles y si el título no promete más que el contenido. Incluye sugerencias menores, si existen, en explanation sin crear un defecto bloqueante por estilo, puntuación, pequeñas repeticiones o una cita oficial válida sin ancla. Usa defects y approved=false si la redacción es materialmente incomprensible o engañosa, si la repetición confunde condiciones, o si un título o llamada a la acción contiene afirmaciones engañosas. Nunca rebajes un criterio legal para mejorar legibilidad.'''


def normalized(s):
    return ' '.join(re.findall(r'\w+', ''.join(c for c in unicodedata.normalize('NFKD',str(s).lower()) if not unicodedata.combining(c))))


def join_fields(*fields):
    # Only exact duplicate strings inside a paragraph. No semantic deletion.
    result=[]
    for value in fields:
        if value and value not in result: result.append(value)
    return ' '.join(result)


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.ids=set();self.links={};self.active=None;self.parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if attrs.get('id'): self.ids.add(attrs['id'])
        if attrs.get('name') and tag=='a': self.ids.add(attrs['name'])
        if tag=='a':
            href=attrs.get('href',''); self.active=href[1:] if href.startswith('#') else None;self.parts=[]
    def handle_data(self,data):
        if self.active:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.active:
            self.links.setdefault(self.active,set()).add(normalized(' '.join(self.parts))); self.active=None


def html_anchor(record, html):
    """Use an observed API block ID only if the official HTML TOC and target agree."""
    url=record.get('official_url',''); api=record.get('api_url',''); doc=record.get('source_id',''); article=str(record.get('article',''))
    p=urlsplit(url); a=urlsplit(api)
    if (doc not in NAMES or p.scheme!='https' or p.netloc!='www.boe.es' or p.path!='/buscar/act.php'
        or parse_qs(p.query).get('id')!=[doc] or a.scheme!='https' or a.netloc!='www.boe.es'
        or not a.path.startswith('/datosabiertos/api/legislacion-consolidada/id/'+doc+'/texto/bloque/')
        or not re.fullmatch(r'\d+',article)): return None
    block=unquote(a.path.rsplit('/',1)[-1]);
    if not re.fullmatch(r'[A-Za-z0-9_-]+',block):return None
    parser=Anchors(); parser.feed(html)
    if block in parser.ids and 'articulo '+article in parser.links.get(block,set()):
        return url.split('#')[0]+'#'+block
    return None


class CitationResolver:
    def __init__(self,opener=None):self.opener=opener;self.pages={};self.report={}
    def resolve(self,record):
        eid=record['evidence_id']
        if eid in self.report:return self.report[eid]['url']
        url=record['official_url']; doc=record.get('source_id'); status='OFFICIAL_DOCUMENT_FALLBACK'
        if doc in NAMES and self.opener:
            if url not in self.pages:
                self.pages[url]=''
                try:
                    with self.opener(Request(url,headers={'User-Agent':'LexGo official citation verification'}),timeout=8) as r:
                        # Require same official document, no offsite or cross-document redirects.
                        end=urlsplit(r.geturl()); start=urlsplit(url)
                        if (end.scheme,end.netloc,end.path,parse_qs(end.query).get('id'))==(start.scheme,start.netloc,start.path,parse_qs(start.query).get('id')):
                            body=r.read(8_000_001)
                            if len(body)<=8_000_000:self.pages[url]=body.decode('utf-8',errors='replace')
                except Exception:pass
            try:direct=html_anchor(record,self.pages[url])
            except (ValueError,TypeError):direct=None
            if direct:url=direct;status='VERIFIED_ARTICLE_ANCHOR'
        elif doc not in NAMES:status='OFFICIAL_SOURCE_URL'
        self.report[eid]={'evidence_id':eid,'article':record.get('article'),'url':url,'status':status,'source_url':record['official_url']}
        return url


def label(p):
    doc=p['document_reference']; article=p['article_reference']
    if article:return f"Artículo {article} {'del' if doc==RD else 'de la' if doc==LO else 'de'} {NAMES.get(doc,doc or 'la norma citada')}"
    return str(p.get('source_title') or doc or 'Fuente oficial')


def opening(title):
    # Neutral, topic-specific fallback; never introduces new legal claims.
    subject=title[:1].lower()+title[1:]
    if subject.startswith(('renovación','modificación','prórroga','residencia')):subject='la '+subject
    return f'¿Tienes dudas sobre {subject.rstrip("?.")}? Aquí te explicamos qué debes tener en cuenta y qué cuestiones conviene revisar en tu caso.'


def quality(article):
    paras=[(p['claim_id'],join_fields(p['text'],p['conditions'],p['exceptions'])) for s in article['sections'] for p in s['paragraphs']]
    duplicates=[]; sentences=[]
    for cid,txt in paras:
        for sentence in re.split(r'(?<=[.!?])\s+',txt):
            n=normalized(sentence)
            if len(n.split())>=6:sentences.append((cid,n))
    for i,(cid,txt) in enumerate(sentences):
        for other,previous in sentences[:i]:
            if txt==previous or (len(txt)>55 and SequenceMatcher(None,txt,previous,autojunk=False).ratio()>=.9):
                duplicates.append({'claim_id':cid,'similar_to':other,'kind':'EXACT' if txt==previous else 'NEAR_MATCH','text':txt[:180]});break
    words=sum(len(t.split()) for _,t in paras)
    long=sum(len(t.split())>32 for _,t in sentences)
    return {'advisory_only':True,'word_count_legal_paragraphs':words,'long_sentence_count':long,'repetition_signals':duplicates,
            'intro_mode':'EVIDENCE_LINKED' if article.get('intro_claim') else 'TOPIC_SPECIFIC_FALLBACK',
            'note':'Heuristic only; no legal content deleted. Minor style does not block legal approval.'}
