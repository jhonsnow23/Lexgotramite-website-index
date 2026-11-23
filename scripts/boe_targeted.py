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

def article_from_id(identifier):
    """BOE block identifiers such as a21, accepted only for precept blocks."""
    m = re.fullmatch(r'a([1-9]\d{0,2})', identifier, re.I)
    return int(m.group(1)) if m else None

def block_index(root):
    """Read BOE index XML. Prefer the printed article title, then standard aNN IDs.

    The official index uses <bloque><id>a22</id><titulo>Artículo 22</titulo>.
    Some consolidated indexes differ in formatting or punctuation.
    """
    matches = {}
    for node in root.iter():
        if lname(node.tag) not in ('bloque', 'item', 'elemento'):
            continue
        ident = value(node, ('id_bloque', 'id'))
        if not ident or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', ident):
            continue
        title = value(node, ('titulo', 'titulo_bloque', 'descripcion', 'nombre'))
        m = ARTICLE_RE.search(clean_text(title))
        by_title = int(m.group(1)) if m else None
        by_id = article_from_id(ident)
        if by_title is not None and by_id is not None and by_title != by_id:
            raise ValueError('BOE index article title/id conflict')
        number = by_title if by_title is not None else by_id
        if number is None:
            continue
        if number in matches and matches[number] != ident:
            raise ValueError('Ambiguous BOE article identifiers')
        matches[number] = ident
    return matches

def parse_version_date(value):
    """BOE API dates are YYYYMMDD; accept ISO solely for legacy fixtures."""
    s = str(value or '').strip()
    if not s:
        return None
    if re.fullmatch(r'\d{8}', s):
        fmt = '%Y%m%d'
    elif re.fullmatch(r'\d{4}-\d{2}-\d{2}', s):
        fmt = '%Y-%m-%d'
    else:
        raise ValueError('Malformed BOE version date')
    try:
        return datetime.strptime(s, fmt).date()
    except ValueError as err:
        raise ValueError('Invalid BOE version date') from err

def _visible_text(version):
    """Extract official provision text, not footnotes or editorial annotations."""
    ignored = {'blockquote', 'script', 'style', 'img'}
    parts = []
    def walk(n, in_ignored=False):
        if in_ignored or lname(n.tag) in ignored:
            return
        # In BOE XML, legal text is generally direct HTML <p> and <table> descendants.
        if lname(n.tag) in ('p', 'table', 'texto', 'contenido', 'parrafo'):
            if not any(lname(a.tag) in ignored for a in n.iter() if a is not n):
                t = clean_text(' '.join(n.itertext()))
                if t and t not in parts: parts.append(t)
            return
        if n.text and n.text.strip() and lname(n.tag) not in ('version', 'bloque'):
            t = clean_text(n.text)
            if t: parts.append(t)
        for child in n:
            walk(child)
    walk(version)
    return '\n'.join(parts).strip()

def latest_block_text(root):
    """Select the latest safely identifiable BOE version.

    BOE fecha_publicacion / fecha_vigencia attributes are optional. A single
    undated version can be read but its effective status is NOT verified.
    Multiple versions with missing dates are ambiguous and must fail closed.
    """
    versions = elements(root, 'version')
    if versions:
        dated=[]
        for node in versions:
            pub = parse_version_date(value(node, ('fecha_publicacion',)))
            vig = parse_version_date(value(node, ('fecha_vigencia',)))
            dated.append((vig or pub, pub, node))
        if len(dated) > 1 and any(row[0] is None for row in dated):
            raise ValueError('BOE versions lack dates: cannot determine latest safely')
        if len(dated) > 1:
            dated.sort(key=lambda x:(x[0], x[1] or x[0]))
            if dated[-1][:2] == dated[-2][:2]:
                raise ValueError('Ambiguous current BOE block version')
        root = dated[-1][2]
    result = _visible_text(root)
    if len(result) < 55:
        raise ValueError('Empty or insufficient BOE legal block')
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
