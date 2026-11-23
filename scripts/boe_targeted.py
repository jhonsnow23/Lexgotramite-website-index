"""Bounded BOE consolidated-legislation *block* retriever.

The BOE consolidated text is informative, not an authoritative determination of
legal applicability. This module does not validate substantive legal claims.
"""
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import urlsplit, quote
from urllib.request import Request, urlopen
import re
import xml.etree.ElementTree as ET

API = 'https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/'
DOC_RE = re.compile(r'^BOE-A-\d{4}-\d+$')
ARTICLE_RE = re.compile(r'\bArt[ií]culo\s+(\d{1,3})\b', re.I)
MAX_INDEX = 2_000_000
MAX_BLOCK = 700_000
MAX_ARTICLES = 12
MAX_TOTAL = 26_000

class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(); self.items = []
    def handle_data(self, data):
        self.items.append(data)

def clean_text(data):
    if '<' in data and '>' in data:
        h = TextOnly(); h.feed(data); data='\n'.join(h.items)
    return re.sub(r'\s+', ' ', data).strip()

def lname(tag):
    return str(tag).split('}')[-1].lower()

def elements(root, tag):
    return [e for e in root.iter() if lname(e.tag)==tag]

def value(node, names):
    for name in names:
        for k,v in node.attrib.items():
            if lname(k)==name and v.strip(): return v.strip()
        for e in node:
            if lname(e.tag)==name and e.text and e.text.strip(): return e.text.strip()
    return ''

def fetch_xml(url, max_bytes, *, opener=urlopen):
    if urlsplit(url).scheme != 'https' or urlsplit(url).hostname not in ('www.boe.es','boe.es') or not url.startswith(API):
        raise ValueError('BOE API URL not allowed')
    req=Request(url, headers={'Accept':'application/xml,text/xml','User-Agent':'LexGoTramite OfficialSourceResearch/1.0'})
    with opener(req,timeout=24) as response:
        final=response.geturl()
        if urlsplit(final).hostname not in ('www.boe.es','boe.es') or urlsplit(final).scheme!='https':
            raise ValueError('BOE redirected outside allowed official host')
        b=response.read(max_bytes+1)
        if len(b)>max_bytes: raise ValueError('BOE API response exceeds bounded retrieval limit')
    if b'<!DOCTYPE' in b.upper() or b'<!ENTITY' in b.upper():
        raise ValueError('Unexpected XML DTD or entity')
    try: return ET.fromstring(b), sha256(b).hexdigest()
    except ET.ParseError as err: raise ValueError('Invalid official BOE XML') from err

def block_index(root):
    """Accept BOE index block identifiers and descriptive titles, no fuzzy article guessing."""
    matches={}
    for node in root.iter():
        if lname(node.tag) not in ('bloque','item','elemento'): continue
        ident=value(node,('id_bloque','id'))
        title=value(node,('titulo','titulo_bloque','descripcion','nombre'))
        if not title:
            title=' '.join((node.text or '', ' '.join((e.text or '') for e in node if lname(e.tag) in ('titulo','cabecera'))))
        m=re.search(r'\bArt[ií]culo\s+(\d{1,3})(?!\d)',clean_text(title),re.I)
        if m and ident and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',ident):
            matches.setdefault(int(m.group(1)),ident)
    return matches

def latest_block_text(root):
    """Choose latest dated version, if API supplies versions; reject ambiguous duplicates."""
    versions=elements(root,'version')
    if versions:
        dated=[]
        for node in versions:
            d=value(node,('fecha_publicacion','fecha_vigencia','fecha'))
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',d):
                raise ValueError('BOE version date missing: cannot select latest safely')
            dated.append((d,node))
        dated.sort(key=lambda x:x[0])
        if len(dated)>1 and dated[-1][0]==dated[-2][0]:
            raise ValueError('Ambiguous current BOE block version')
        root=dated[-1][1]
    # prefer the actual legal text node, excluding annotations and metadata
    candidates=[]
    for tag in ('texto','contenido','parrafo'):
        candidates=elements(root,tag)
        if candidates: break
    nodes=candidates if candidates else [root]
    texts=[]
    for node in nodes:
        raw=' '.join(node.itertext())
        if raw.strip(): texts.append(clean_text(raw))
    result='\n'.join(dict.fromkeys(texts))
    if len(result)<55: raise ValueError('Empty or insufficient BOE legal block')
    return result

def retrieve_articles(doc_id, numbers, *, opener=urlopen, max_total=MAX_TOTAL):
    if not DOC_RE.fullmatch(doc_id): raise ValueError('Invalid BOE document identifier')
    numbers=list(dict.fromkeys(int(n) for n in numbers))
    if not numbers or len(numbers)>MAX_ARTICLES or any(n<1 or n>999 for n in numbers):
        raise ValueError('Unsupported article selection')
    index_url=f'{API}{doc_id}/texto/indice'
    index,_=fetch_xml(index_url,MAX_INDEX,opener=opener)
    ids=block_index(index)
    missing=[n for n in numbers if n not in ids]
    if missing: raise ValueError('Requested BOE articles absent from index: '+','.join(map(str,missing)))
    records=[];total=0
    for number in numbers:
        block_id=quote(ids[number],safe='')
        url=f'{API}{doc_id}/texto/bloque/{block_id}'
        node,digest=fetch_xml(url,MAX_BLOCK,opener=opener)
        text=latest_block_text(node)
        # Never emit clipped passages as complete legislation
        if total+len(text)>max_total: raise ValueError('Requested legal evidence exceeds model context budget')
        total+=len(text)
        records.append({'article':str(number),'text':text,'api_url':url,'sha256':digest,
            'legal_status':'UNVERIFIED','retrieved_at':datetime.now(timezone.utc).isoformat()})
    return {'source_id':doc_id,'official_url':f'https://www.boe.es/buscar/act.php?id={doc_id}',
            'informative_consolidation':True,'provisions':records,
            'evidence_text':'\n\n'.join(f'Artículo {r["article"]}.\n{r["text"]}' for r in records)}
