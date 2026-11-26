"""Run 66: fail-closed publication of trusted, settled Run 65+ drafts.
No model calls. Only the dedicated publication job gets a write token.
"""
import argparse
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urldefrag

import knowledge_hub_v50 as hub
import first_article_v50 as engine
import weekly_content_v50 as weekly
import evidence_passages_v50 as passages

POLICY = 'v66-autonomous-1'
SOURCES = {'daily': ('lexgo-seo-v50.yml', weekly.DAILY, 'KNOWLEDGE_ARTICLE'),
           'weekly': ('lexgo-weekly-blog-v50.yml', weekly.WEEKLY, 'WEEKLY_BLOG')}
REPO = 'jhonsnow23/Lexgotramite-website-index'
# Explicit one-time owner-authorized migration of the four supplied real drafts.
# Only hashes of article/review/evidence are stored, not private draft contents.
LEGACY_BACKLOG = {
 'fa83fcadd512b1ed108fd220f0a70c5980cc80559ad7835a97750816347d22fa': ('5d8dfcb690d54556e0e683e1f42de0b899aa7759e0742298c998dafdf88996b9','6d8f67c9efc3ca79d4d56bb83ea43eed4fa98ba43a775b1557b8c3929e9a5f34'),
 'af0200ffe12f3f9a088c2c07946535022fe906676d446dd23e6a17d1f495b770': ('a50eb83b18609526f3912155a536b8c983eb74af4efb985bb0f854ea86841a3c','e12a2e7ad28308c90fed847e2e3bb265f1b532e738837f6bf0bbffed31c4d9ff'),
 '0a2e35541775bc09275758591350ee8150488908ab8ee0712c22ee3f8ab47b83': ('acb3eeda263742308bc01d3d98bda0ab0b8db05e1e889c45dd851163a1e63fb6','7cc138677d5d83426bc4052a9e95d899449ef71e2971154c4cbb560eaa2da823'),
 '520e21011893a1b268ec240340a7a6fb33af379330e5a2f06843539c2bfe47e2': ('d6c42a34176a507edfed1e8af20078b3ac6cecfeea2409df69b5a5b4e8e06266','a3b239f31ef5929074284c8ca32cf2ed904a209fdf90423ad02ee9ad85c9ef0f'),
}
FIRST_LEGACY = next(iter(LEGACY_BACKLOG))

FILES = ('article.json','article_metadata.json','legal_review.json','decision.json','evidence.json',
         'evidence_passage_catalog.json','claim_evidence_matrix.json','citation_validation_report.json',
         'editorial_quality_report.json','passage_aliases.json')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def enabled():
    return os.environ.get('LEXGO_AUTOPUBLISH_ENABLED') == 'true'


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True, timeout=90).strip()


def validate_run(data, kind, current_id, repo=REPO):
    rid = str(data['id'])
    require(data['head_branch'] == 'main' and data['head_repository']['full_name'].lower() == repo.lower()
            and data['path'].split('@',1)[0] == '.github/workflows/'+('lexgo-first-article-v50.yml' if kind=='first_article' else SOURCES[kind][0])
            and data['event'] in ('schedule','workflow_dispatch')
            and (data['status'] == 'completed' or (rid == current_id and data['status'] == 'in_progress')),
            'Untrusted source workflow')
    return rid


def validate_budget(reservation, settlement, summary, usage, kind, rid):
    require(reservation['allowed'] is True and reservation['kind'] == settlement['kind'] == kind
            and str(reservation['run_id']) == str(settlement['run_id']) == rid
            and reservation['date'] == settlement['date']
            and reservation['slot'] == weekly.slot(kind, datetime.fromisoformat(reservation['date']).date())
            and all(x['publication_allowed'] is False for x in (reservation,settlement,summary,usage)),
            'Missing or inconsistent budget authorization')
    debit = weekly.money(settlement['debit_usd']); reserve=weekly.money(reservation['reserved_usd'])
    require(0 < debit <= reserve <= weekly.CAPS[kind] and
            debit == weekly.money(usage['conservative_budget_debit_usd']) == weekly.money(summary['conservative_budget_debit_usd'])
            and weekly.money(settlement['estimated_cost_usd']) == weekly.money(usage['estimated_usd']) == weekly.money(summary['estimated_cost_usd'])
            and summary['simulated'] is False and summary['result']=='REVIEW_READY'
            and summary['articles_independently_approved']==1 and summary['api_calls']==len(usage['calls'])
            and summary['api_calls']>=2 and any(c.get('stage')=='legal_review' and c.get('status')=='COMPLETED' for c in usage['calls']),
            'Review-ready usage or settlement mismatch')
    return reservation['slot']


def validate_evidence(folder,backlog=False):
    a,m,kind,approval = hub.approved_source(folder)
    evidence=hub.read(folder/'evidence.json'); cat=hub.read(folder/'evidence_passage_catalog.json')
    matrix=hub.read(folder/'claim_evidence_matrix.json'); review=hub.read(folder/'legal_review.json')
    if backlog:
        require(LEGACY_BACKLOG.get(a['content_hash'])==(engine.digest(review),engine.digest(evidence)), 'Backlog article/review/evidence hash mismatch')
    old=backlog and a['content_hash']==FIRST_LEGACY
    citation_report=[] if old else hub.read(folder/'citation_validation_report.json')
    quality=None if old else hub.read(folder/'editorial_quality_report.json')
    aliases=hub.read(folder/'passage_aliases.json')
    require(matrix['publication_allowed'] is False and (old or (quality['independent_review_passed'] is True
            and quality['simulated'] is False and quality['article_hash']==a['content_hash'])), 'Editorial or claim report mismatch')
    require(m.get('duplicate') is not True and m.get('publication_allowed') is False, 'Duplicate or invalid metadata')
    claims={c['claim_id']:c for c in matrix['claims']}
    paras=[p for s in a['sections'] for p in s['paragraphs']]
    require(len(claims)==len(matrix['claims'])==len(paras)>0 and set(claims)=={p['claim_id'] for p in paras},'Claim inventory mismatch')
    by_id={e['evidence_id']:e for e in evidence}; require(len(by_id)==len(evidence),'Duplicate evidence IDs')
    used={}
    def check_citation(c):
        pid=c['passage_id']; resolved=passages.resolve_passage(pid,cat,evidence)
        require(resolved is not None, 'Unverifiable official passage')
        eid=resolved['evidence_id']; rec=by_id[eid]
        require(hub.official.allowed(c['url']), 'Invalid citation URL')
        if c['url']!=rec['official_url']:
            require(any(x.get('evidence_id')==eid and x.get('url')==c['url'] and x.get('source_url')==rec['official_url']
                        and x.get('status')=='VERIFIED_ARTICLE_ANCHOR' for x in citation_report),'Unverified article anchor')
        require(not engine.official_metadata_conflict(rec),'Adverse official metadata')
        used.setdefault(eid,set()).add(c['url'])
        return resolved
    for s in a['sections']:
        engine.plain(s['heading'])
        for p in s['paragraphs']:
            c=claims[p['claim_id']]
            for k in ('text','conditions','exceptions'):engine.plain(p[k],allow_empty=k!='text')
            require(c['verification']=='AUTOMATED_REVIEW_SUPPORTED' and c['claim']==p['text'] and c['section']==s['heading']
                    and c['conditions']==p['conditions'] and c['exceptions']==p['exceptions'], 'Claim prose mismatch')
            resolved=[check_citation(x) for x in p['citations']]
            require(bool(resolved) and resolved==c['passages'] and {x['evidence_id'] for x in resolved}==set(c['evidence_ids']), 'Claim passage mismatch')
    for g in a['limitations']:
        engine.plain(g['text'],allow_empty=True)
        require(not g['text'] or bool(g['citations']), 'Uncited material limitation')
        for c in g['citations']:check_citation(c)
    engine.plain(a['introduction'],allow_empty=True);engine.plain(a.get('disclaimer',''),allow_empty=old)
    require(engine.blocking_gap_checks_pass(review['verdict'],[{'gap_id':g} for g in review.get('blocking_gap_ids',[])],aliases), 'Unresolved material gap')
    require(bool(used),'Missing supporting sources')
    # Store only source descriptors and text hashes, not private research, publicly.
    refs=[]
    for eid in sorted(used):
        r=by_id[eid]
        refs.append({'source_id':r['source_id'],'article':r.get('article'),'official_url':r['official_url'],
                     'authority':r['authority'],'document_title':r['document_title'],
                     'text_hash':passages.digest(r['text']),'retrieved_at':r['retrieved_at'],'citation_urls':sorted(used[eid])})
    return a,m,kind,approval,refs


def fresh_sources(refs, temp):
    """Re-fetch every cited source before publishing; fail on a material text change.
    No AI calls. A changed or unavailable source must be researched again, not ignored.
    """
    researcher=engine.OfficialResearch(engine.Ledger(engine.Limits(documents=65,minutes=8),Path(temp)))
    resolver=hub.editorial.CitationResolver(opener=researcher.opener)
    for r in refs:
        require(hub.official.allowed(r['official_url']),'Unofficial revalidation URL')
        if r['source_id'] in (engine.RD,engine.LO) and str(r['article']).isdigit():
            current=researcher.article(r['source_id'],int(r['article']))
        else:
            current=engine.graph.split_rd316_evidence([hub.official.retrieve_one(r['authority'],r['document_title'],r['official_url'])])
        matches=[x for x in current if x.get('source_id')==r['source_id'] and x.get('article')==r['article'] and passages.digest(x['text'])==r['text_hash']
                    and not engine.official_metadata_conflict(x)]
        require(bool(matches), 'Official source changed or could not be revalidated')
        for url in r.get('citation_urls',[]):
            if url!=r['official_url']:require(resolver.resolve(matches[0])==url,'Official article anchor no longer verified')


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__();self.ids=set();self.hrefs=[];self.canon=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.add(a['id'])
        if tag=='a' and 'href' in a:self.hrefs.append(a['href'])
        if tag=='link' and a.get('rel')=='canonical':self.canon.append(a.get('href'))


def url_file(root,url):
    u=urlsplit(url);require(not u.netloc and u.path.startswith('/') and '..' not in u.path.split('/'), 'Invalid internal URL')
    p=root/u.path.lstrip('/')
    if u.path.endswith('/'):p=p/'index.html'
    elif not p.is_file():p=p.with_suffix('.html')
    require(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve()),'Missing internal URL: '+url)
    if u.fragment:require(u.fragment in Links(p.read_text(encoding='utf-8')).ids,'Missing internal anchor: '+url)
    return p


def sitemap(root):
    x=ET.parse(root/'sitemap.xml').getroot(); loc=[n.text for n in x.iter() if n.tag.split('}')[-1]=='loc']
    require(len(loc)==len(set(loc)) and all(loc),'Invalid sitemap');return set(loc)


def changed(root):
    return sorted(set(git(root,'diff','--name-only','HEAD').splitlines()+git(root,'ls-files','--others','--exclude-standard').splitlines()))


def validate_site(root, before_rows, old_sitemap, row):
    files=changed(root)
    allowed={'index.html','sitemap.xml',hub.INVENTORY,hub.BASE.strip('/')+'/index.html'}
    allowed|={hub.cat_url(c).strip('/')+'/index.html' for c in hub.CATEGORIES}
    if row['content_type']=='WEEKLY_BLOG':allowed|={'blog/index.html','publish_state.json'}
    if '#' not in row['url']:allowed.add(row['url'].strip('/')+'.html')
    require(bool(files) and set(files)<=allowed,'Unexpected publication file changes')
    require(all((root/f).is_file() and not (root/f).is_symlink() for f in files),'Deleted or unsafe publication file')
    rows=hub.inventory(root)
    require(len(rows)==len(before_rows)+1 and rows[:-1]==before_rows and rows[-1]==row,'Existing inventory modified')
    require(old_sitemap<=sitemap(root),'Existing sitemap entry removed')
    # No changes outside the intended homepage blocks (including work/reviews).
    def outside(text):
        text=re.sub(re.escape(hub.START)+r'[\s\S]*?'+re.escape(hub.END),'[HUB]',text,count=1)
        if row['content_type']=='WEEKLY_BLOG':text=re.sub(r'<!-- Blog -->[\s\S]*?<!-- Cita \(Zoho Bookings\) -->','[BLOG]',text,count=1)
        return text
    require(outside(git(root,'show','HEAD:index.html')).strip()==outside((root/'index.html').read_text(encoding='utf-8')).strip(),'Unrelated homepage changed')
    for r in rows:
        p=url_file(root,r['url']);parsed=Links(p.read_text(encoding='utf-8'))
        require(parsed.canon==[hub.SITE+urldefrag(r['url'])[0]],'Incorrect canonical')
        require(hub.SITE+urldefrag(r['url'])[0] in sitemap(root),'Missing sitemap entry')
    # Validate links newly introduced on the newly rendered guide/article pages.
    for f in files:
        if not f.endswith('.html') or f in ('index.html','blog/index.html'):continue
        parsed=Links((root/f).read_text(encoding='utf-8'))
        for href in parsed.hrefs:
            if href.startswith('/') and not href.startswith('//'):url_file(root,href)
            elif href.startswith('#'):require(href[1:] in parsed.ids,'Missing local anchor')
            elif href.startswith(('https://','http://')):require(hub.official.allowed(href) or urlsplit(href).hostname=='lexgotramite.com' or f.startswith('blog/'),'Invalid external guide link')
            else:require(not re.match(r'(?i)\s*(javascript|data|vbscript):',href),'Unsafe link')
    return files


def prepare(folder,root,kind,rid,source_slot,refs,review_hash,now=None,backlog=False):
    require(enabled(),'Automatic publication disabled')
    root=Path(root);require(not git(root,'status','--porcelain'),'Publication needs a clean checkout')
    a,m,actual,approval,actual_refs=validate_evidence(folder,backlog)
    require(actual==SOURCES[kind][2] and actual_refs==refs,'Wrong content destination or evidence changed')
    require(review_hash==engine.digest(hub.read(Path(folder)/'legal_review.json')),'Review hash changed')
    day=now or weekly.local_today(); slot=weekly.slot(kind,day); rows=hub.inventory(root)
    if any(r['content_hash']==a['content_hash'] or r.get('source_run_id')==rid for r in rows):return None,[],'ALREADY_COMMITTED'
    if not backlog and any(r['content_type']==actual and r.get('publication_authorization',{}).get('mode')!='BACKLOG_MIGRATION' and weekly.slot(kind,datetime.fromisoformat(r['published_at']).date())==slot for r in rows):return None,[],'PUBLICATION_SLOT_USED'
    dup,_,_=engine.seo.classify_duplicate({'proposed_title':a['title'],'primary_query':m.get('primary_query') or a['title']},engine.seo.metadata_inventory(root))
    require(not dup,'Duplicate search intent')
    auth={'policy':POLICY,'state':'AUTOMATED_PUBLICATION_AUTHORIZED','article_hash':a['content_hash'],'approval_hash':approval,
          'review_hash':review_hash,'evidence_hash':engine.digest(refs),'source_run_id':rid,'source_slot':source_slot,
          'publication_slot':slot,'content_type':actual,'source_refs':refs,'human_approved':False,
          'mode':'BACKLOG_MIGRATION' if backlog else 'SCHEDULED',
          'budget_authorization':'OWNER_AUTHORIZED_HISTORICAL_NO_NEW_API_SPEND' if backlog else 'SETTLED_RESERVATION'}
    prior=sitemap(root); row=hub.publish(folder,approval,root,authorization=auth)
    return row,validate_site(root,rows,prior,row),'WEBSITE_VALIDATION_PASSED'


def unpack(gh,art,kind,rid,temp,backlog=False,source_kind=None):
    """Never extract arbitrary ZIP paths; read exact, unique JSON members only."""
    with gh.archive(art) as z:
        first=source_kind=='first_article'
        prefix='' if first else 'seo_v50/article/' if kind=='daily' else 'article/'
        summary=weekly.find_json(z,prefix+'run_summary.json');usage=weekly.find_json(z,'usage.json' if first else prefix+'api_usage.json')
        if backlog:
            require(summary['result']=='REVIEW_READY' and summary['simulated'] is False and summary['articles_independently_approved']==1
                    and summary['publication_allowed'] is False and usage['publication_allowed'] is False
                    and summary['api_calls']==len(usage['calls']) and any(c.get('stage')=='legal_review' and c.get('status')=='COMPLETED' for c in usage['calls']), 'Historical real review not established')
            slot='historical:'+str(rid)
        else:
            res=weekly.find_json(z,'v65-budget/reservation.json');settle=weekly.find_json(z,'v65-budget/settlement.json')
            slot=validate_budget(res,settle,summary,usage,kind,rid)
        ready=[t for t in summary['topics_attempted'] if t['result']=='REVIEW_READY']
        require(len(ready)==1,'Ambiguous approved article')
        name=ready[0]['artifact_directory'];require(bool(re.fullmatch(r'topic_\d+_[a-z0-9_]+',name)),'Invalid article directory')
        folder=Path(temp)/'source';folder.mkdir(exist_ok=True)
        a=weekly.find_json(z,prefix+name+'/article.json')
        if backlog:require(a.get('content_hash') in LEGACY_BACKLOG,'Not an authorized historical draft')
        old=backlog and a.get('content_hash')==FIRST_LEGACY
        for f in FILES:
            if old and f in ('citation_validation_report.json','editorial_quality_report.json'):continue
            hub.save(folder/f,weekly.find_json(z,prefix+name+'/'+f))
        return folder,slot


def verify_live(root,row,attempts=8):
    url=hub.SITE+row['url']; file=url_file(root,row['url']); local=file.read_text(encoding='utf-8')
    # Full content hash marker appears in the published HTML, not just the title.
    marker='data-lexgo-content-hash="'+row['content_hash']+'"'
    for i in range(attempts):
        try:
            req=urllib.request.Request(urldefrag(url)[0]+'?lexgo_verify='+row['content_hash'][:16],headers={'Cache-Control':'no-cache','User-Agent':'LexGo-v66-verifier'})
            with urllib.request.urlopen(req,timeout=15) as response:
                live=response.read(3_000_000).decode('utf-8');status=response.status; host=urlsplit(response.url).hostname
            if status==200 and host=='lexgotramite.com' and marker in live and marker in local and Links(live).canon==Links(local).canon:
                return True
        except (OSError,ValueError):pass
        if i+1<attempts:time.sleep(20)
    return False


def execute(kind,root,out,backlog=False):
    report={'policy':POLICY,'kind':'backlog' if backlog else kind,'state':'PUBLICATION_DISABLED','public_url_verified':False,'attempts':[],'publications':[]}
    def save():hub.save(out,report)
    save()
    if not enabled():return 0
    report['state']='CHECKING_TRUSTED_ARTIFACTS';save()
    require(os.environ.get('GITHUB_REPOSITORY','').lower()==REPO.lower() and os.environ.get('GITHUB_REF')=='refs/heads/main','Unauthorized repository or ref')
    current=os.environ['GITHUB_RUN_ID'];gh=weekly.GitHub();day=weekly.local_today();root=Path(root)
    rows=hub.inventory(root)
    current_slot=weekly.slot(kind,day)
    prior=[r for r in rows if r['content_type']==SOURCES[kind][2] and r.get('publication_authorization',{}).get('mode')!='BACKLOG_MIGRATION' and weekly.slot(kind,datetime.fromisoformat(r['published_at']).date())==current_slot]
    if prior and not backlog:
        row=prior[-1];report.update(state='PUBLIC_URL_VERIFIED' if verify_live(root,row,2) else 'DEPLOYMENT_PENDING',public_url=hub.SITE+row['url']);report['public_url_verified']=report['state']=='PUBLIC_URL_VERIFIED';save();return 0
    # Current run first, then recover recent trusted results without paying again.
    if backlog and set(LEGACY_BACKLOG)<={r['content_hash'] for r in rows}:
        report['state']='BACKLOG_ALREADY_IMPORTED';save();return 0
    arts=[(a,kind) for a in gh.list(SOURCES[kind][1])]
    if backlog:arts.extend((a,'first_article') for a in gh.list('lexgo-v50-first-article-results'))
    arts=sorted(arts,key=lambda x:(str(x[0]['workflow_run']['id'])==current,x[0]['created_at']),reverse=True)
    for art,source_kind in arts[:80 if backlog else 20]:
        rid=str(art['workflow_run']['id'])
        if art.get('expired') or not day-timedelta(days=14 if kind=='weekly' else 7)<=weekly.madrid_day(art['created_at'])<=day or any(r.get('source_run_id')==rid for r in rows):continue
        require(rid.isdigit(),'Invalid run ID')
        try:
            data=json.loads(gh.fetch(f'https://api.github.com/repos/{REPO}/actions/runs/{rid}'));validate_run(data,source_kind,current)
            with tempfile.TemporaryDirectory() as td:
                folder,slot=unpack(gh,art,kind,rid,td,backlog,source_kind);a,m,actual,approval,refs=validate_evidence(folder,backlog)
                fresh_sources(refs,td)
                review_hash=engine.digest(hub.read(folder/'legal_review.json'))
                row,files,state=prepare(folder,root,kind,rid,slot,refs,review_hash,backlog=backlog)
                if not row:report['attempts'].append({'run_id':rid,'state':state});continue
                report.update(state=state,source_run_id=rid,article_hash=row['content_hash'],public_url=hub.SITE+row['url'],files=files);save()
                require(enabled(),'Automatic publication disabled before commit')
                git(root,'add','--',*files)
                git(root,'-c','user.name=lexgo-content[bot]','-c','user.email=41898282+github-actions[bot]@users.noreply.github.com','commit','-m',f'LexGo: publish {kind} {row["content_hash"][:12]}')
                require(enabled(),'Automatic publication disabled before push')
                git(root,'push','origin','HEAD:refs/heads/main')
                report.update(state='COMMIT_PUSHED',commit=git(root,'rev-parse','HEAD'));save()
                ok=verify_live(root,row,2 if backlog else 8);report.update(state='PUBLIC_URL_VERIFIED' if ok else 'DEPLOYMENT_PENDING',public_url_verified=ok)
                report['publications'].append({'article_hash':row['content_hash'],'commit':report['commit'],'url':report['public_url'],'public_url_verified':ok});save()
                if not backlog:return 0
                rows=hub.inventory(root)
                if set(LEGACY_BACKLOG)<={r['content_hash'] for r in rows}:break
                report['state']='CHECKING_TRUSTED_ARTIFACTS'
        except Exception as exc:
            # Never log raw network errors or credentials. A mutated checkout is
            # abandoned, not reused for a different candidate; no force push.
            report['attempts'].append({'run_id':rid,'state':'BLOCKED_OR_RETRY_PENDING','error':type(exc).__name__,'reason':str(exc) if isinstance(exc,ValueError) else 'See workflow diagnostics'})
            save()
            if git(root,'status','--porcelain') or report.get('state') in ('WEBSITE_VALIDATION_PASSED','COMMIT_PUSHED'):
                report['state']='PUBLICATION_FAILED';save();return 1
    if backlog:
        report['missing_backlog_hashes']=sorted(set(LEGACY_BACKLOG)-{r['content_hash'] for r in hub.inventory(root)})
        report['state']='BACKLOG_PARTIAL' if report['missing_backlog_hashes'] else 'BACKLOG_IMPORTED'
    else:report['state']='NO_ELIGIBLE_REVIEWED_ARTICLE'
    save();return 0


def monitor(root,out,limit=8):
    groups={}
    for row in hub.inventory(root):
        for ref in row.get('publication_authorization',{}).get('source_refs',[]):
            key=engine.digest({k:v for k,v in ref.items() if k!='retrieved_at'})
            g=groups.setdefault(key,{'ref':ref,'urls':[]});g['urls'].append(row['url'])
    keys=sorted(groups); start=((weekly.local_today().toordinal()//7)*limit)%len(keys) if keys else 0
    chosen=(keys[start:]+keys[:start])[:limit]; checks=[]
    with tempfile.TemporaryDirectory() as td:
        for key in chosen:
            g=groups[key]
            try:fresh_sources([g['ref']],td);state='UNCHANGED'
            except Exception:state='REVALIDATION_REQUIRED'
            checks.append({'official_url':g['ref']['official_url'],'article':g['ref']['article'],'affected_urls':g['urls'],'state':state})
    recent=[r for r in hub.inventory(root)[-8:] if r.get('publication_authorization')]
    deployments=[{'url':r['url'],'public_url_verified':verify_live(root,r,1)} for r in recent]
    hub.save(out,{'source_groups':len(keys),'checked':len(checks),'checks':checks,'deployment_rechecks':deployments,'paid_api_calls':0,'automatic_withdrawal':False})
    return 0


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('kind',choices=[*SOURCES,'monitor']);p.add_argument('output',type=Path);p.add_argument('--backlog',action='store_true');a=p.parse_args()
    if a.kind=='monitor':raise SystemExit(monitor(hub.ROOT,a.output))
    if a.backlog and a.kind!='daily':p.error('Backlog applies only to knowledge articles')
    raise SystemExit(execute(a.kind,hub.ROOT,a.output,a.backlog))
