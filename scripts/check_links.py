#!/usr/bin/env python3
"""Validate local published links without treating extensionless routes as missing.
Usage: python scripts/check_links.py [--report PATH] [--strict-fragments]
Only standard library; no site changes or network requests.
"""
import argparse
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
HOSTS = {'lexgotramite.com', 'www.lexgotramite.com'}
ATTRS = {'a': ('href',), 'link': ('href',), 'img': ('src', 'srcset'), 'source': ('src', 'srcset'), 'script': ('src',), 'iframe': ('src',), 'form': ('action',), 'video': ('src', 'poster'), 'audio': ('src',)}

class Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.ids = set()
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if d.get('id'): self.ids.add(d['id'])
        if tag == 'a' and d.get('name'): self.ids.add(d['name'])
        for attr in ATTRS.get(tag, ()):
            if d.get(attr):
                values = [item.strip().split()[0] for item in d[attr].split(',')] if attr == 'srcset' else [d[attr]]
                self.links.extend((tag, attr, value) for value in values if value)

def page_url(path):
    rel = path.relative_to(ROOT).as_posix()
    if rel == 'index.html': return '/'
    if rel.endswith('/index.html'): return '/' + rel[:-10]
    return '/' + rel.removesuffix('.html')

def resolve(source, url):
    u = urlsplit(url.strip())
    if u.scheme and u.scheme.lower() not in ('http','https'): return 'excluded', None, u.fragment
    if u.netloc and (u.hostname or '').lower() not in HOSTS: return 'external', None, u.fragment
    path = unquote(u.path)
    if not path and not u.netloc: return 'fragment', source, u.fragment
    if not path and u.netloc: path = '/'
    target = ROOT / path.lstrip('/') if path.startswith('/') or u.netloc else source.parent / path
    target = target.resolve()
    if not target.is_relative_to(ROOT): return 'missing', str(target), u.fragment
    candidates = [target]
    if target.is_dir(): candidates.insert(0, target / 'index.html')
    elif not target.suffix: candidates.extend([Path(str(target)+'.html'), target / 'index.html'])
    for candidate in candidates:
        if candidate.is_file() and candidate.is_relative_to(ROOT): return 'found', candidate, u.fragment
    return 'missing', target, u.fragment

def audit(strict_fragments=False):
    issues=[];counts=Counter(); pages={}; graph={}
    for file in sorted(ROOT.rglob('*.html')):
        if '.git' in file.parts: continue
        c=Collector();c.feed(file.read_text(encoding='utf-8'))
        pages[file]=c
    for source,c in pages.items():
        rel=source.relative_to(ROOT).as_posix(); graph[rel]=[]
        for tag,attr,url in c.links:
            if url.strip().startswith(('#',)):
                status,target,fragment='fragment',source,url.strip()[1:]
            else:status,target,fragment=resolve(source,url)
            counts[status]+=1
            if status == 'found' and target.suffix == '.html':graph[rel].append(target.relative_to(ROOT).as_posix())
            if status == 'missing': issues.append({'type':'missing_local_target','source':rel,'element':tag,'attribute':attr,'url':url,'resolved':str(target.relative_to(ROOT)) if isinstance(target,Path) and target.is_relative_to(ROOT) else str(target)})
            if strict_fragments and status in ('found','fragment') and fragment and isinstance(target,Path) and target.suffix=='.html' and target in pages and unquote(fragment) not in pages[target].ids:
                issues.append({'type':'missing_fragment','source':rel,'url':url,'fragment':fragment})
    try:
        sitemap = ElementTree.parse(ROOT/'sitemap.xml')
        for el in sitemap.findall('.//{*}loc'):
            if el.text:
                status,target,_=resolve(ROOT/'index.html',el.text)
                counts['sitemap_'+status]+=1
                if status == 'missing':issues.append({'type':'missing_sitemap_target','source':'sitemap.xml','url':el.text})
    except (OSError,ElementTree.ParseError) as exc:issues.append({'type':'invalid_sitemap','details':str(exc)})
    canonical_mismatch=[]
    for source,c in pages.items():
        match=re.search(r'<link\b[^>]*rel=["\']canonical["\'][^>]*>',source.read_text(encoding='utf-8'),re.I)
        if match:
            link=re.search(r'href=["\']([^"\']+)',match.group(),re.I)
            if link:
                got=urlsplit(link.group(1)).path.rstrip('/') or '/'
                expected=page_url(source).rstrip('/') or '/'
                if got != expected:
                    canonical_mismatch.append({'page':source.relative_to(ROOT).as_posix(),'canonical':link.group(1),'expected_route':expected})
    return {'html_files':len(pages),'link_counts':dict(counts),'broken_links':issues,'broken_count':len(issues),'canonical_route_mismatches_for_review':canonical_mismatch,'dependency_map':graph}

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',default='reports/link-audit.json');p.add_argument('--strict-fragments',action='store_true');args=p.parse_args()
    result=audit(args.strict_fragments)
    out=ROOT/args.report;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f"HTML: {result['html_files']} | broken internal references: {result['broken_count']} | canonical mismatches (review only): {len(result['canonical_route_mismatches_for_review'])}")
    for issue in result['broken_links'][:30]:print('BROKEN',issue.get('source'),issue.get('url',issue.get('details')))
    print('Report:',out.relative_to(ROOT))
    return 1 if result['broken_count'] else 0
if __name__=='__main__':sys.exit(main())
