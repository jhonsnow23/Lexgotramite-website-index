#!/usr/bin/env python3
"""Lex Go Trámite v5.0 orchestrator: demand-driven, draft-only, fail-closed.

Reuses the verified-data parser and scoring from v4.2; records *outcomes*, not
selections, so unsuccessful drafts never create 60-day publication cooldowns.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import unicodedata
from io import BytesIO
import json
import os
from pathlib import Path
import re
import urllib.request
import urllib.parse
import urllib.error
import zipfile

try:
    import seo_v42 as baseline
    import legal_content_v50 as generator
except ImportError:
    from scripts import seo_v42 as baseline
    from scripts import legal_content_v50 as generator

try:
    from temporary_residence_policy_v50 import classify, SEEDS
except ImportError:
    from scripts.temporary_residence_policy_v50 import classify, SEEDS

VERSION='5.0.0'
ARTIFACT='lexgo-v50-results'
PUBLISHED={'PUBLISHED','PUBLISHED_VERIFIED','SUBSTANTIVE_UPDATE_PUBLISHED'}
ATTEMPTED={'DRAFT_FAILED','BLOCKED_RETRIEVAL','BLOCKED_VALIDATION','BLOCKED_INSUFFICIENT_EVIDENCE','BLOCKED_APPLICABILITY','BLOCKED_LEGAL_VALIDATION','ERROR','REVIEW_READY','DRAFT_ATTEMPTED'}


def events(history):
    return baseline.prior_history(history)


def recent_event(e,today):
    try:
        d=date.fromisoformat(e.get('date') or e.get('selected_on'))
    except (ValueError,TypeError):
        return None
    gap=(today-d).days
    return gap if gap>=0 else None


def topic_blocker(item,history,today,*,ignore_attempt_backoff=False):
    for e in events(history):
        age=recent_event(e,today)
        if age is None:continue
        same_cluster=e.get('cluster_id')==item['cluster_id']
        # Search Console associated URLs are NOT article identities. Different
        # intent clusters often share the same service landing page. Never
        # conflate them when computing publication or failed-attempt cooldowns.
        if not same_cluster:continue
        status=e.get('status') or 'DRAFT_ATTEMPTED' # migrate v4.2 ambiguous selection-only history safely
        if status in PUBLISHED and age<60 and not e.get('material_legal_change_verified',False):
            return 'Published-page cooldown (60 days)'
        if status in ATTEMPTED and age<1 and not ignore_attempt_backoff:
            return 'Draft attempt already made today; retry tomorrow or use manual retry'
    return None


# Only URL paths and their slugs are inspected. Never open HTML bodies.
META_STOP={'de','del','en','la','las','el','los','un','una','y','por','para',
           'como','que','segun','espana','espanola','espanol','tramites',
           'requisitos','guia','solicitud','verificar','oficial','adecuada'}
META_EQUIV={'renovar':'renov','renovacion':'renov','renovaciones':'renov',
            'documentos':'document','documentacion':'document',
            'tipos':'tipo','autorizaciones':'autorizacion'}

def slug_words(value):
    norm=''.join(c for c in unicodedata.normalize('NFKD',str(value).lower())
                 if not unicodedata.combining(c))
    words=re.findall(r'[a-z0-9]+',norm)
    return {META_EQUIV.get(w,w) for w in words if len(w)>2 and w not in META_STOP}


def proposed_slug(title):
    text=''.join(c for c in unicodedata.normalize('NFKD',title.lower())
                 if not unicodedata.combining(c))
    return '-'.join(re.findall(r'[a-z0-9]+',text))


def metadata_inventory(root):
    """Enumerate paths only; never load a current or old blog's content."""
    base=Path(root)
    candidates=list(base.glob('blog/*.html'))+list(base.glob('*.html'))
    return sorted({p.relative_to(base).as_posix() for p in candidates if p.is_file()})


def classify_duplicate(item,existing_urls):
    """Distinguish same search intent from mere Google page association.

    This is a conservative metadata classifier, not semantic page analysis.
    Strong overlap with an existing blog slug blocks a draft. A broad service
    landing page does not automatically block a specific informational query.
    """
    topic=slug_words(item['proposed_title'])
    query=slug_words(item.get('primary_query',''))
    slug=proposed_slug(item['proposed_title'])
    prospective='blog/'+slug+'.html'
    if prospective in existing_urls:
        return True,'Exact proposed URL already exists',prospective
    # All site blog slugs can signal duplicate intents, not only the URL that
    # Search Console happened to associate with a query.
    for path in existing_urls:
        if not path.startswith('blog/') or not path.endswith('.html'):
            continue
        other=slug_words(Path(path).stem)
        if not other:continue
        common=len(topic & other)
        # A query-specific qualifying focus absent from a generic blog slug
        # (e.g. 'permanente' versus generic 'renovar residencia') may be a
        # separate article, even when Search Console attributed the query there.
        novelty=query-other-{'legal','general','actual','nuevo','nueva','informacion','espana'}
        if novelty:
            continue
        if path in item.get('existing_pages',[]) and len(query)<=2 and query and query & other and len(query & other)>=len(query)-1:
            return True,'Broad query overlaps existing blog topic; distinct focus not proven',path
        if common>=2 and common/max(len(other),1)>=0.8 and common/max(len(topic),1)>=0.45:
            return True,'Existing blog slug targets substantially the same intent',path
        # Catch direct query/slug equivalence when the suggested title adds SEO wording.
        qcommon=len(query & other)
        if qcommon>=2 and qcommon/max(len(query),1)>=0.8 and qcommon/max(len(other),1)>=0.8:
            return True,'Existing blog slug matches the Google query intent',path
    return False,'Distinct informational intent; Google associated URL is not a duplicate',prospective


def supports_research(item):
    # This is a source REGISTRY coverage check, NOT proof of legal applicability.
    p={'proposals':[{'cluster_id': item['cluster_id'], 'origin_cluster_id':item['cluster_id'],
        'proposed_title':item['proposed_title'], 'action':'create_article',
        'queries':item['supporting_queries'], 'search_demand_evidence':{
            'impressions_28d':item['impressions_28d'],
            'impressions_90d':item['impressions_90d']}}]}
    return generator.plan(p)['source_registry_complete'],p


def choose(report,catalog,website,history,today,*,retry_failed=False):
    # Reuse factual GSC metrics / service filtering, but never reuse the obsolete
    # v4.1 coverage gate or the selection-only 60-day history logic.
    ranked=baseline.rank(report,catalog,website,[],today)
    result=[];winner=None;proposal=None
    inventory=metadata_inventory(website)
    for item in ranked:
        row=dict(item)
        row.pop('v41_evidence_coverage_candidate',None)
        row['score_breakdown']=dict(row['score_breakdown'])
        row['score_breakdown']['cooldown_penalty']=0
        row['score']=sum(v for k,v in row['score_breakdown'].items() if k!='cooldown_penalty')
        row['cooldown_active']=False
        # Align the draft question with observed demand. A prewritten generic
        # title must not silently change the question that Google users asked.
        demand_words=slug_words(row.get('primary_query',''))
        title_words=slug_words(row.get('proposed_title',''))
        if demand_words and len(demand_words & title_words)/len(demand_words)<0.65:
            row['original_suggested_title']=row['proposed_title']
            row['proposed_title']=row['primary_query'].strip().capitalize()+': información y trámites oficiales'
            row['title_adjusted_to_query']=True
        else:
            row['title_adjusted_to_query']=False
        row['commercial_classification']=classify(row['proposed_title'], [row.get('primary_query','')]+row.get('supporting_queries',[]), row['cluster_id'])
        row['research_registry_available'],candidate=(supports_research(row) if not row['commercial_classification']['excluded'] else (False,None))
        duplicate,dup_reason,proposed_path=classify_duplicate(row,inventory)
        row['duplicate_metadata_detected']=duplicate
        row['duplicate_metadata_reason']=dup_reason
        row['proposed_new_path']=proposed_path
        block=topic_blocker(row,history,today,ignore_attempt_backoff=retry_failed)
        if row['commercial_classification']['excluded']:
            row['recommended_action']='SKIP';row['selection_reason']=row['commercial_classification']['exclusion_reason']
        elif block:
            row['recommended_action']='MONITOR';row['selection_reason']=block
        elif duplicate:
            row['recommended_action']='SKIP';row['selection_reason']=dup_reason+' (metadata-only; no blog body read)'
        elif not row['research_registry_available']:
            row['recommended_action']='MONITOR';row['selection_reason']='Source registry needs expansion; no unsupported legal guesswork'
        elif row['impressions_28d']<3 and row['impressions_90d']<30:
            row['recommended_action']='MONITOR';row['selection_reason']='Insufficient observed demand for an automatic draft'
        else:
            row['recommended_action']='CREATE_NEW_ARTICLE'
            row['selection_reason']='Distinct intent, measured GSC demand; official-source research still required'
            if winner is None:
                winner=row;proposal=candidate
                # Only safe create-new proposal reaches the generator. Associated
                # URLs remain in diagnostic rows, never as rewrite instructions.
                proposal['proposals'][0]['proposed_path']=proposed_path
                proposal['proposals'][0]['commercial_classification']=row['commercial_classification']
        result.append(row)
    # Rank business priority first, GSC score second. Never choose excluded demand.
    eligible=[x for x in result if x['recommended_action']=='CREATE_NEW_ARTICLE']
    eligible.sort(key=lambda x:(x['commercial_classification']['priority'],-x['score']))
    if eligible:
        winner=eligible[0]
        _,proposal=supports_research(winner)
        proposal['proposals'][0]['proposed_path']=winner['proposed_new_path']
        proposal['proposals'][0]['commercial_classification']=winner['commercial_classification']
    else:
        winner=None;proposal=None
    return result,winner,proposal


class ArtifactRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,hdrs,newurl):
        redirected=super().redirect_request(req,fp,code,msg,hdrs,newurl)
        if redirected and urllib.parse.urlparse(req.full_url).hostname != urllib.parse.urlparse(newurl).hostname:
            for key in list(redirected.headers):
                if key.lower() in ('authorization','cookie','proxy-authorization'):del redirected.headers[key]
        return redirected


def load_history(*,token=None,repository=None,fetch=None):
    token=token if token is not None else os.environ.get('GH_HISTORY_TOKEN')
    repository=repository if repository is not None else os.environ.get('GITHUB_REPOSITORY')
    if not token or not repository or not re.fullmatch(r'[\w.-]+/[\w.-]+',repository):
        return [],'Local mode; no artifact history credentials'
    if fetch is None:
        opener=urllib.request.build_opener(ArtifactRedirect())
        def fetch(url):
            req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token,
                     'Accept':'application/vnd.github+json','User-Agent':'lexgo-v50'})
            with opener.open(req,timeout=30) as response:return response.read()
    try:
        for name,legacy in ((ARTIFACT,False),('lexgo-v42-results',True)):
            url=f'https://api.github.com/repos/{repository}/actions/artifacts?name={name}&per_page=100'
            listing=json.loads(fetch(url))
            if 'artifacts' not in listing:raise ValueError('GitHub artifact list lacks artifacts')
            for art in sorted(listing['artifacts'],key=lambda x:x.get('created_at',''),reverse=True):
                if art.get('expired'):continue
                with zipfile.ZipFile(BytesIO(fetch(art['archive_download_url']))) as z:
                    matches=[x for x in z.namelist() if x.endswith('/history.json') or x=='history.json']
                    if not matches:continue
                    value=json.loads(z.read(matches[0]));out=events(value)
                    if legacy:
                        out=[dict(e,status=e.get('status','DRAFT_ATTEMPTED')) for e in out]
                    return out,'Restored '+name+' history'
        return [],'No previous artifacts exist; new history'
    except Exception as exc:
        raise RuntimeError('History recovery failed; fail closed: '+type(exc).__name__) from exc


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def select(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    report=baseline.validate_report(json.loads(Path(args.report).read_text(encoding='utf-8')))
    catalog=json.loads(Path(args.catalog).read_text(encoding='utf-8'))
    today=date.fromisoformat(args.today) if args.today else date.today()
    if args.history:
        history=events(json.loads(Path(args.history).read_text(encoding='utf-8')));origin='Provided history'
    else:
        history,origin=load_history()
        if args.require_history and origin.startswith('Local mode'):
            raise RuntimeError('Required GitHub history credential missing')
    rows,chosen,proposal=choose(report,catalog,args.website_root,history,today,retry_failed=args.retry_failed)
    # A source-backed editorial seed may be tested without claiming GSC demand.
    # It remains a draft, and all evidence/validation gates still apply.
    if chosen is None:
        inventory=metadata_inventory(args.website_root)
        for key,seed in SEEDS.items():
            item={'cluster_id':'seed_'+key,'proposed_title':seed['proposed_title'],
                  'primary_query':seed['primary_query'],'supporting_queries':[seed['primary_query']],
                  'impressions_28d':0,'impressions_90d':0,'existing_pages':[],
                  'score':0,'score_breakdown':{},'search_demand_verified':False}
            policy=classify(item['proposed_title'],[item['primary_query']],item['cluster_id'])
            duplicate,_,path=classify_duplicate(item,inventory)
            if duplicate or topic_blocker(item,history,today,ignore_attempt_backoff=args.retry_failed):continue
            available,candidate=supports_research(item)
            if not available:continue
            item.update(commercial_classification=policy,recommended_action='CREATE_NEW_ARTICLE',
                selection_reason='Editorial seed; NO verified Search Console demand',
                proposed_new_path=path,research_registry_available=True)
            candidate['proposals'][0].update(commercial_classification=policy,proposed_path=path)
            rows.append(item);chosen=item;proposal=candidate;break

    save(out/'ranked_opportunities.json',{'version':VERSION,'metadata':report['metadata'],'opportunities':rows})
    # Keep history unchanged until the candidate finishes: a selection is not an outcome.
    save(out/'history.json',{'version':VERSION,'events':history[-200:]})
    save(out/'selection.json',{'version':VERSION,'selected':chosen,'history_origin':origin,
         'retry_failed':args.retry_failed,'publication_allowed':False})
    if proposal:save(out/'selected_proposal.json',proposal)
    entries=[];used=set()
    for x in rows:
        if x['recommended_action'] not in ('CREATE_NEW_ARTICLE','IMPROVE_EXISTING_ARTICLE'):continue
        if set(x.get('existing_pages',[])) & used:continue
        entries.append(x);used.update(x.get('existing_pages',[]))
    dates=[today+timedelta(days=i) for i in range(30) if (today+timedelta(days=i)).weekday() in (0,2,4)]
    save(out/'editorial_calendar.json',{'version':VERSION,'generated_on':today.isoformat(),'days':30,
         'entries':[{'date':dt.isoformat(),'cluster':x['cluster_id'],'topic':x['proposed_title'],
                     'action':x['recommended_action'],'status':'DRAFT_ONLY'} for dt,x in zip(dates,entries[:12])]})
    print(json.dumps({'version':VERSION,'selected':chosen['cluster_id'] if chosen else None,
        'candidate_count':len(entries),'history':origin,'publication_allowed':False}))
    return 0


def finalize(args):
    out=Path(args.output);selection=json.loads((out/'selection.json').read_text(encoding='utf-8'))
    history=events(json.loads((out/'history.json').read_text(encoding='utf-8')))
    selected=selection['selected']
    if selected:
        decision_path=Path(args.decision)
        try:
            decision=json.loads(decision_path.read_text(encoding='utf-8'))
            result=decision.get('result','ERROR')
        except (FileNotFoundError,ValueError):result='ERROR'
        if result=='REVIEW_READY':status='REVIEW_READY'
        elif result=='BLOCKED_RETRIEVAL':status='BLOCKED_RETRIEVAL'
        elif result in ('BLOCKED_INSUFFICIENT_EVIDENCE','BLOCKED_IRRELEVANT_OR_INCOMPLETE_EVIDENCE'):
            status='BLOCKED_INSUFFICIENT_EVIDENCE'
        elif result=='BLOCKED_APPLICABILITY':status='BLOCKED_APPLICABILITY'
        elif result=='BLOCKED_LEGAL_VALIDATION':status='BLOCKED_LEGAL_VALIDATION'
        elif result=='SKIPPED_DUPLICATE_TOPIC':status='DRAFT_FAILED'
        elif result=='BLOCKED_VALIDATION':status='BLOCKED_VALIDATION'
        else:status='DRAFT_FAILED'
        history.append({'date':date.today().isoformat(),'selected_on':date.today().isoformat(),
            'cluster_id':selected['cluster_id'],'existing_page':None,
            'status':status,'published':False,'publication_allowed':False,'generator_result':result})
    save(out/'history.json',{'version':VERSION,'events':history[-200:]})
    save(out/'run_summary.json',{'version':VERSION,'selected_cluster':selected['cluster_id'] if selected else None,
        'result':history[-1]['status'] if selected else 'NO_ELIGIBLE_TOPIC',
        'publication_allowed':False,'note':'Review-ready does not mean legally certified'})
    print((out/'run_summary.json').read_text(encoding='utf-8'))
    return 0


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=('select','finalize'))
    p.add_argument('--report',default='reports/seo_intelligence.json')
    p.add_argument('--catalog',default='config/seo_v42_services.json')
    p.add_argument('--website-root',default='.')
    p.add_argument('--output',default='reports/seo_v50')
    p.add_argument('--decision',default='reports/seo_v50/article/decision.json')
    p.add_argument('--history',default='')
    p.add_argument('--today',default='')
    p.add_argument('--require-history',action='store_true')
    p.add_argument('--retry-failed',action='store_true')
    args=p.parse_args(argv)
    return select(args) if args.action=='select' else finalize(args)

if __name__=='__main__':raise SystemExit(main())
