#!/usr/bin/env python3
"""Fail-closed, offline validation for proposed Lex Go Trámite HTML content.

This is NOT a legal fact checker. Official citations and exact evidence snippets are
necessary but insufficient for substantive legal accuracy. No publication occurs here.
"""
import argparse
import datetime as dt
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ALLOWED = {
    'boe.es', 'www.boe.es', 'inclusion.gob.es', 'www.inclusion.gob.es',
    'migraciones.gob.es', 'www.migraciones.gob.es', 'administracion.gob.es',
    'sede.administracionespublicas.gob.es', 'mjusticia.gob.es',
    'www.mjusticia.gob.es', 'sede.mjusticia.gob.es', 'policia.es',
    'www.policia.es', 'sede.policia.gob.es', 'exteriores.gob.es',
    'www.exteriores.gob.es', 'seg-social.es', 'www.seg-social.es',
    'interior.gob.es', 'www.interior.gob.es', 'eur-lex.europa.eu',
    'europa.eu', 'www.europa.eu',
}
# Official ministry subdomains may be added after reviewing ownership; no suffix-based
# wildcard for arbitrary domains, because that admits lookalike hosts.

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = {}
        self.links = []
        self.meta = []
        self.text = []
        self.headings = []
        self._heading = None
        self._capturing_title = False
        self.title = ''
        self._ignore = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags[tag] = self.tags.get(tag, 0) + 1
        if tag in ('script', 'style'):
            self._ignore += 1
        if tag == 'a':
            self.links.append(attrs.get('href', ''))
        if tag == 'meta':
            self.meta.append(attrs)
        if tag in ('h1','h2','h3'):
            self._heading = [tag, '']
        if tag == 'title':
            self._capturing_title = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self._ignore:
            self._ignore -= 1
        if self._heading is not None and tag == self._heading[0]:
            self.headings.append(tuple(self._heading))
            self._heading = None
        if tag == 'title':
            self._capturing_title = False

    def handle_data(self, data):
        if self._capturing_title:
            self.title += data
        if self._ignore:
            return
        if self._heading:
            self._heading[1] += data
        self.text.append(data)


def norm(s):
    return ' '.join(str(s).split()).casefold()


def is_official(url):
    try:
        parts = urlsplit(url)
        return (parts.scheme == 'https' and parts.hostname in ALLOWED
                and not parts.username and not parts.password
                and parts.port in (None, 443))
    except (ValueError, TypeError):
        return False


def validate(item, html, today=None):
    today = today or dt.date.today()
    errors = []
    page = Page()
    page.feed(html)
    if not item.get('title') or not item.get('meta_description'):
        errors.append('Missing title or meta_description in manifest')
    if page.tags.get('h1', 0) != 1:
        errors.append('Expected exactly one H1')
    if page.tags.get('h2', 0) < 2:
        errors.append('Expected at least two H2 headings')
    if len(norm(' '.join(page.text))) < 700:
        errors.append('Body appears too short for a complete guide')
    if not page.title.strip():
        errors.append('HTML title tag missing')
    if not any(m.get('name','').casefold() == 'description' and m.get('content','').strip() for m in page.meta):
        errors.append('Meta description tag missing')
    if 'fuentes oficiales' not in norm(' '.join(page.text)):
        errors.append('Missing visible Fuentes oficiales section')
    if re.search(r'\b(?:lorem ipsum|todo:|pendiente de verificar|\[insert|\[fuente)\b', html, re.I):
        errors.append('Contains placeholders or unverified text')
    if item.get('publication_allowed') is True:
        errors.append('Do not set publication_allowed=true in a draft manifest')
    if item.get('reviewed_by_lawyer') is True and not item.get('review_record'):
        errors.append('Unverified claim of professional review')
    sources = item.get('sources', [])
    if not isinstance(sources, list) or not sources:
        errors.append('No official sources supplied')
        sources = []
    ids = set()
    for index, source in enumerate(sources):
        sid = source.get('id')
        if not sid or sid in ids:
            errors.append(f'Source {index}: missing or duplicate id')
        ids.add(sid)
        url = source.get('url', '')
        if not is_official(url):
            errors.append(f'Source {index}: source URL not on reviewed allowlist')
        if url not in page.links:
            errors.append(f'Source {index}: official URL not clickable in article')
        if not source.get('title') or not source.get('document_reference'):
            errors.append(f'Source {index}: missing document title or reference')
        try:
            accessed = dt.date.fromisoformat(source.get('accessed', ''))
            if accessed > today or (today - accessed).days > 14:
                errors.append(f'Source {index}: evidence retrieval date is stale or in future')
        except ValueError:
            errors.append(f'Source {index}: bad retrieval date')
        # This exact text MUST come from a real fetched official source, but offline
        # validation cannot prove provenance. A later online verifier must do so.
        if len(norm(source.get('evidence_excerpt', ''))) < 40:
            errors.append(f'Source {index}: insufficient verbatim evidence excerpt')
    claims = item.get('legal_claims', [])
    if not claims:
        errors.append('No traceable legal claims')
    for index, claim in enumerate(claims):
        if not claim.get('claim') or not claim.get('evidence_excerpt'):
            errors.append(f'Claim {index}: missing claim or evidence')
        if claim.get('source_id') not in ids:
            errors.append(f'Claim {index}: source id not found')
        if norm(claim.get('claim', '')) not in norm(' '.join(page.text)):
            errors.append(f'Claim {index}: claim text absent from HTML')
        relevant = next((s for s in sources if s.get('id') == claim.get('source_id')), None)
        if relevant and norm(claim.get('evidence_excerpt','')) not in norm(relevant.get('evidence_excerpt','')):
            errors.append(f'Claim {index}: excerpt not present in source record')
    if item.get('legal_uncertainty') or item.get('source_conflict'):
        errors.append('Unresolved legal uncertainty or source conflict')
    if item.get('duplicate_topic'):
        errors.append('Possible duplication of existing article')
    return errors


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', required=True)
    p.add_argument('--html', required=True)
    p.add_argument('--output', default='')
    args = p.parse_args()
    item = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    html = Path(args.html).read_text(encoding='utf-8')
    errs = validate(item, html)
    output = {'status': 'BLOCKED' if errs else 'PRELIMINARY_CHECKS_PASSED',
              'publication_allowed': False,
              'limitations': ['This gate does NOT independently authenticate source evidence',
                              'This gate does NOT establish substantive legal accuracy',
                              'No publication action is implemented'],
              'errors': errs}
    if args.output:
        Path(args.output).write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 1 if errs else 0

if __name__ == '__main__':
    sys.exit(main())
