"""BOE consolidated-law provision locator. Retrieval != legal applicability verification.

Read-only, bounded, official API only. Designed to be called by boe_targeted.py.
"""
import datetime as dt
import hashlib
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE='https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/'
DOC=re.compile(r'BOE-A-\d{4}-\d+\Z')
HEADING=re.compile(r'\bArt(?:[íi]culo|\.)\s*(\d{1,4})(?:\s*(bis|ter|qu[aá]ter))?\b',re.I)
MAX_INDEX=4_000_000
MAX_BLOCK=800_000
MAX_ARTICLES=12
MAX_CONTEXT=40_000
# Narrow, explicit support for older Civil Code headings written as words.
SPELLED = {'veintiuno':21,'veintiún':21,'veintiun':21,'veintidós':22,'veintidos':22,'veintitrés':23,'veintitres':23}
WORD_HEADING=re.compile(r'\bArt(?:[íi]culo|\.)\s+([A-Za-záéíóúüñ]+)\b',re.I)
BLOCK_ID=re.compile(r'a(\d{1,4})(bis|ter|quater)?\Z',re.I)


class BOEError(RuntimeError):
    def __init__(self,code,detail,*,url=''):
        super().__init__(f'{code}: {detail}');self.code=code;self.url=url


def tag(elem): return elem.tag.rsplit('}',1)[-1].lower() if isinstance(elem.tag,str) else ''
def txt(node): return ' '.join(' '.join(node.itertext()).split())

def _attr(node,*keys):
    for k,v in node.attrib.items():
        if k.rsplit('}',1)[-1].lower() in keys and str(v).strip():return str(v).strip()
    return ''

def _direct(node,*keys):
    for c in node:
        if tag(c) in keys and txt(c): return txt(c)
    return ''

def api_get(url, *, opener=urllib.request.urlopen, limit=MAX_INDEX):
    u=urllib.parse.urlsplit(url)
    if u.scheme!='https' or u.hostname not in ('www.boe.es','boe.es') or not u.path.startswith('/datosabiertos/api/legislacion-consolidada/id/'):
        raise BOEError('BAD_URL','Only official BOE consolidated legislation endpoints accepted',url=url)
    req=urllib.request.Request(url,headers={'Accept':'application/xml, text/xml','User-Agent':'LexGoTramite-LegalResearch/4.5 (https://lexgotramite.com)'})
    try:
        with opener(req,timeout=25) as resp:
            final=urllib.parse.urlsplit(resp.geturl())
            if final.scheme!='https' or final.hostname not in ('www.boe.es','boe.es'):
                raise BOEError('UNSAFE_REDIRECT','BOE API redirected to nonofficial host',url=url)
            raw=resp.read(limit+1)
    except urllib.error.HTTPError as e:raise BOEError('HTTP_ERROR',f'HTTP {e.code}',url=url) from e
    except (urllib.error.URLError,TimeoutError) as e:raise BOEError('NETWORK_ERROR',type(e).__name__,url=url) from e
    if len(raw)>limit:raise BOEError('RESPONSE_TOO_LARGE',f'Exceeded {limit} bytes',url=url)
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise BOEError('XML_UNSAFE','DTD or entity declarations forbidden',url=url)
    try:root=ET.fromstring(raw)
    except ET.ParseError as e:raise BOEError('MALFORMED_XML',str(e)[:90],url=url) from e
    for e in root.iter():
        if tag(e)=='code' and e.text and e.text.strip() not in ('200','') and tag(root) in ('response','respuesta'):
            raise BOEError('API_ERROR',f'API status {e.text.strip()}',url=url)
    return root,hashlib.sha256(raw).hexdigest()


def _identifier(n):
    return _attr(n,'id_bloque','identificador','id') or _direct(n,'id_bloque','identificador','id')

def _caption(n):
    return _attr(n,'titulo','titulo_bloque','nombre','descripcion') or _direct(n,'titulo','titulo_bloque','nombre','descripcion','rotulo')

def _number_of(s):
    m=HEADING.search(s or '')
    if m:return (int(m.group(1)),(m.group(2) or '').lower())
    w=WORD_HEADING.search(s or '')
    if w and w.group(1).lower() in SPELLED:return (SPELLED[w.group(1).lower()],'')
    return None

def index_map(root):
    """Extract article=>block IDs from leaf-like index records.

    Never derive the number from a generic aNN ID alone: it may be an unrelated
    structure and earlier attempts trusted that guess. Header must identify it.
    """
    result={}; candidates=[]; index_ids={}
    for n in root.iter():
        if tag(n) not in ('bloque','item','elemento','entrada','registro','precepto','articulo','artículo'):
            continue
        bid=_identifier(n)
        title=_caption(n)
        if not bid or not re.fullmatch(r'[A-Za-z0-9_-]{1,90}',bid):continue
        bm=BLOCK_ID.fullmatch(bid)
        if bm:
            key=(int(bm.group(1)),(bm.group(2) or '').lower())
            if key in index_ids and index_ids[key]!=bid:
                raise BOEError('AMBIGUOUS_INDEX',f'Conflicting article block candidates for {key}')
            index_ids[key]=bid
        header=_number_of(title)
        if not header:
            # Some BOE index records embed labels one extra level down.
            for c in n:
                if tag(c) in ('texto','rotulo','epigrafe','epígrafe','nombre','caption'):
                    header=_number_of(txt(c))
                    if header:break
        if header:candidates.append((header,bid,title))
    for key,bid,title in candidates:
        if key in result and result[key]!=bid:
            raise BOEError('AMBIGUOUS_INDEX',f'Conflicting block IDs for Artículo {key[0]}')
        result[key]=bid
    for key,bid in index_ids.items():
        if key in result and result[key]!=bid:
            raise BOEError('AMBIGUOUS_INDEX',f'Index title conflicts with candidate block ID for {key}')
        # This is only a candidate observed in the actual index.
        # retrieve() independently checks the returned article heading.
        result.setdefault(key,bid)
    return result


def parse_date(raw):
    s=str(raw or '').strip()
    if not s:return None
    try:
        if re.fullmatch(r'\d{8}',s):return dt.datetime.strptime(s,'%Y%m%d').date()
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',s):return dt.date.fromisoformat(s)
    except ValueError:pass
    raise BOEError('INVALID_VERSION_DATE',f'Unrecognized date {s[:12]}')


def version_nodes(root):
    # A block may have <version> siblings and each version its own date metadata.
    matches=[x for x in root.iter() if tag(x)=='version']
    return matches if matches else [root]


def version_choice(root, *, as_of=None):
    target=as_of or dt.datetime.now(dt.timezone.utc).date()
    versions=version_nodes(root)
    dates=[]
    for node in versions:
        # Both attributes and direct child nodes occur in real/fixture formats.
        start=parse_date(_attr(node,'fecha_vigencia','fecha_inicio','fecha_publicacion') or _direct(node,'fecha_vigencia','fecha_inicio','fecha_publicacion'))
        dates.append((start,node))
    if len(dates)>1 and any(d is None for d,_ in dates):
        raise BOEError('VERSION_UNCERTAIN','Multiple versions and one or more lack applicable dates')
    eligible=[(d,n) for d,n in dates if d is not None and d<=target]
    if len(dates)>1 and not eligible:raise BOEError('VERSION_UNCERTAIN','No applicable version established for selected date')
    if eligible:
        latest=max(d for d,n in eligible)
        chosen=[n for d,n in eligible if d==latest]
        if len(chosen)!=1:raise BOEError('VERSION_UNCERTAIN','Multiple tied versions')
        return chosen[0],latest.isoformat(),'VERSION_DATE_FOUND_NOT_LEGAL_CERTIFICATION'
    return versions[0],None,'VERSION_UNCERTAIN'


def version_text(node):
    # Collect text from paragraph-like elements, skip editorial notes.
    blacklist={'nota','notas','nota_editorial','script','style','blockquote','pie','footnote'}
    blocks=[]
    def walk(n):
        if tag(n) in blacklist:return
        if tag(n) in ('p','parrafo','párrafo','texto','contenido','li'):
            s=txt(n)
            if s and s not in blocks: blocks.append(s)
            return
        for ch in n:walk(ch)
    walk(node)
    if not blocks:
        content=txt(node)
        if content:blocks=[content]
    return '\n'.join(blocks)


def heading_matches(text,article):
    target=(int(article),'')
    # Headings may appear after whitespace or at paragraph beginnings.
    for line in text.splitlines()[:8]:
        match=_number_of(line)
        if match:return match==target
    return False


def retrieve(doc_id, articles, *, opener=urllib.request.urlopen, as_of=None, max_context=MAX_CONTEXT):
    if not DOC.fullmatch(str(doc_id)):raise BOEError('INVALID_DOCUMENT','Invalid document identifier')
    if not articles or len(articles)>MAX_ARTICLES or any(not str(a).isdigit() or not 1<=int(a)<=9999 for a in articles):
        raise BOEError('INVALID_SELECTION','Invalid article numbers')
    selected=list(dict.fromkeys(int(a) for a in articles)); index_url=f'{BASE}{doc_id}/texto/indice'
    root,index_sha=api_get(index_url,opener=opener)
    mapping=index_map(root)
    missing=[n for n in selected if (n,'') not in mapping]
    # No guessed aNN ID fallback. Instead report actual index structure.
    if missing:
        raise BOEError('ARTICLE_NOT_IN_INDEX',f'Could not resolve articles {missing}; {len(mapping)} verified article records indexed',url=index_url)
    output=[]; total=0
    for number in selected:
        blockid=mapping[(number,'')]
        u=f'{BASE}{doc_id}/texto/bloque/{urllib.parse.quote(blockid,safe="")}'
        item,sha=api_get(u,opener=opener,limit=MAX_BLOCK)
        node,version_date,version_status=version_choice(item,as_of=as_of)
        body=version_text(node)
        if not heading_matches(body,number):
            raise BOEError('WRONG_ARTICLE',f'BOE block {blockid} does not contain matching Article {number} heading',url=u)
        if len(body)<45:raise BOEError('INSUFFICIENT_TEXT',f'Article {number} too short',url=u)
        total+=len(body)
        if total>max_context:raise BOEError('CONTEXT_LIMIT','Selected legal provisions exceed AI evidence budget')
        output.append({'source_id':doc_id,'article':str(number),'block_id':blockid,'api_url':u,'text':body,'sha256':sha,'version_date':version_date,'version_status':version_status,'retrieved_at':dt.datetime.now(dt.timezone.utc).isoformat(),'legal_status':'UNVERIFIED'})
    return {'source_id':doc_id,'official_url':f'https://www.boe.es/buscar/act.php?id={doc_id}', 'provisions':output,'index_sha256':index_sha,'evidence_text':'\n\n'.join(f'Artículo {r["article"]}.\n{r["text"]}' for r in output),'informative_consolidation':True}


def probe(doc_id,*,opener=urllib.request.urlopen):
    """Return structural diagnostic only, never full legislative material."""
    url=f'{BASE}{doc_id}/texto/indice'
    try:
        root,hash_=api_get(url,opener=opener)
        counts={}
        for e in root.iter():counts[tag(e)]=counts.get(tag(e),0)+1
        matches=index_map(root)
        examples=[]
        for node in root.iter():
            if tag(node)=='bloque' and len(examples)<8:
                bid=_identifier(node)
                if bid:examples.append({'id':bid[:35],'title':_caption(node)[:110]})
        return {'index_title_examples':examples,'requested_candidates':{str(n):matches.get((n,'')) for n in (21,22,23)},'document':doc_id,'url':url,'root':tag(root),'element_counts':dict(sorted(counts.items(),key=lambda x:-x[1])[:25]),'recognized_article_count':len(matches),'example_article_numbers':[f'{n}{s}' for n,s in list(matches)[:15]],'index_sha256':hash_,'diagnosis':'OK' if matches else 'INDEX_STRUCTURE_UNRECOGNIZED'}
    except BOEError as e:return {'document':doc_id,'url':url,'diagnosis':e.code,'message':str(e)[:220]}

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('--probe',action='store_true');a.add_argument('--doc',default='BOE-A-1889-4763');a.add_argument('--articles',default='21,22,23');a.add_argument('--out',default='reports/boe_v45');args=a.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    result=probe(args.doc)
    (out/'diagnostics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    if args.probe:
        print(json.dumps({'diagnosis':result['diagnosis'],'recognized_article_count':result.get('recognized_article_count',0)}));raise SystemExit(0 if result['diagnosis']=='OK' else 2)
    try:
        details=retrieve(args.doc,args.articles.split(','))
        (out/'evidence.json').write_text(json.dumps(details,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({'result':'evidence_retrieved','provisions':len(details['provisions']),'publication_allowed':False}))
    except BOEError as e:
        (out/'error.json').write_text(json.dumps({'error_code':e.code,'details':str(e),'url':e.url,'publication_allowed':False},ensure_ascii=False,indent=2))
        print(json.dumps({'result':'blocked','error_code':e.code,'publication_allowed':False}));raise SystemExit(2)
