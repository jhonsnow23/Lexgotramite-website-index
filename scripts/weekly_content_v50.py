"""Read-only daily/weekly orchestration; artifact-backed spending reservations."""
import argparse, io, json, math, os, re, sys, urllib.request, zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import seo_v50 as seo
import first_article_v50 as engine
import renewal_intent_v50 as renewal
RES='lexgo-content-reservation-v65'; SET='lexgo-content-settlement-v65'
DAILY='lexgo-v50-results'; WEEKLY='lexgo-v50-weekly-blog-results'
CAPS={'daily':0.15,'weekly':0.25,'diagnostic':0.15}
TITLES={
 'no_lucrativa':'Renovación de residencia no lucrativa: requisitos, plazos y qué debes comprobar antes de solicitarla',
 'cuenta_ajena':'Primera renovación de residencia y trabajo por cuenta ajena: condiciones, plazos y efectos',
 'cuenta_propia':'Renovación de residencia y trabajo por cuenta propia: condiciones, plazos y efectos',
 'arraigo':'Continuidad de residencia por arraigo: opciones de prórroga y modificación según tu autorización',
 'menores_no_nacidos':'Renovación de residencia de hijos menores no nacidos en España: condiciones y continuidad',
 'regularizacion_2026':'Continuidad de residencia tras la regularización extraordinaria de 2026: opciones y condiciones de modificación',
}
def local_today(): return datetime.now(ZoneInfo('Europe/Madrid')).date()
def slot(kind,day): return day.isoformat() if kind!='weekly' else f'{day.isocalendar().year}-W{day.isocalendar().week:02}'
def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,obj): seo.save(Path(path),obj)
def money(value):
    n=float(value)
    if not math.isfinite(n) or n<0: raise ValueError('Invalid budget amount')
    return n
def madrid_day(s): return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(ZoneInfo('Europe/Madrid')).date()
class GitHub:
    def __init__(self):
        repo=os.environ.get('GITHUB_REPOSITORY',''); token=os.environ.get('GH_HISTORY_TOKEN','')
        if not re.fullmatch(r'[\w.-]+/[\w.-]+',repo) or not token: raise ValueError('GitHub artifact access required')
        self.base=f'https://api.github.com/repos/{repo}/actions/artifacts'; self.token=token
        self.opener=urllib.request.build_opener(seo.ArtifactRedirect())
    def fetch(self,url,maxbytes=20_000_000):
        if not url.startswith('https://api.github.com/'): raise ValueError('Invalid artifact API URL')
        req=urllib.request.Request(url,headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','User-Agent':'LexGo-v65'})
        with self.opener.open(req,timeout=45) as r: body=r.read(maxbytes+1)
        if len(body)>maxbytes: raise ValueError('Artifact too large')
        return body
    def list(self,name):
        out=[]
        for page in range(1,21):
            v=json.loads(self.fetch(f'{self.base}?name={name}&per_page=100&page={page}'))
            rows=v['artifacts']; out.extend(rows)
            if len(rows)<100: return out
        raise ValueError('Artifact pagination limit; cannot safely account for history')
    def archive(self,art):
        if art.get('expired'): raise ValueError('Required artifact expired')
        z=zipfile.ZipFile(io.BytesIO(self.fetch(art['archive_download_url'])))
        if sum(x.file_size for x in z.infolist())>40_000_000: z.close(); raise ValueError('Oversized artifact')
        return z
    def records(self,name,filename,start):
        result=[]
        for a in self.list(name):
            if madrid_day(a['created_at'])<start: continue
            with self.archive(a) as z:
                if z.namelist().count(filename)!=1: raise ValueError('Missing or ambiguous ledger record')
                row=json.loads(z.read(filename))
                if str(a['workflow_run']['id'])!=str(row['run_id']):raise ValueError('Ledger artifact/run mismatch')
                if name==RES and date.fromisoformat(row['date'])!=madrid_day(a['created_at']):raise ValueError('Reservation date mismatch')
                result.append(row)
        return result

def calculate(kind,day,start,balance,monthly,reservations,settlements,run_id):
    if kind not in CAPS or not 0<balance<=5 or not 0<monthly<=5 or not 0<=(day-start).days<80:
        raise ValueError('Configure a reconciled <=$5 budget window; renew it before day 80')
    rmap={}; smap={}
    for r in reservations:
        key=str(r['run_id']); d=date.fromisoformat(r['date']); k=r['kind']; cap=money(r['reserved_usd'])
        if key in rmap or k not in CAPS or not start<=d<=day or not 0<cap<=CAPS[k]+1e-8 or r['slot']!=slot(k,d):raise ValueError('Invalid/duplicate reservation')
        rmap[key]=r
    for s in settlements:
        key=str(s['run_id'])
        if key not in rmap or key in smap:raise ValueError('Orphan or duplicate settlement')
        if s['kind']!=rmap[key]['kind'] or s['date']!=rmap[key]['date']:raise ValueError('Settlement mismatch')
        smap[key]=money(s['debit_usd'])
    used=month_used=week_used=0.
    for key,r in rmap.items():
        d=date.fromisoformat(r['date']); debit=smap.get(key,money(r['reserved_usd'])); used+=debit
        if d.strftime('%Y-%m')==day.strftime('%Y-%m'):month_used+=debit
        if slot('weekly',d)==slot('weekly',day):week_used+=debit
        if key==str(run_id) or (r['kind']==kind and r['slot']==slot(kind,day)):
            return {'allowed':False,'reason':'Generation already attempted for this slot; no duplicate paid run','publication_allowed':False}
    remaining=min(balance-used,monthly-month_used,0.35-week_used,CAPS[kind])
    if remaining<0.05: return {'allowed':False,'reason':'Shared conservative budget exhausted','remaining_usd':max(0,remaining),'publication_allowed':False}
    return {'allowed':True,'run_id':str(run_id),'kind':kind,'date':day.isoformat(),'slot':slot(kind,day),'reserved_usd':round(remaining,6),'window_start':start.isoformat(),'prior_debit_usd':round(used,6),'prior_month_debit_usd':round(month_used,6),'prior_week_debit_usd':round(week_used,6),'publication_allowed':False}

def prepare(kind,path):
    today=local_today(); start=date.fromisoformat(os.environ['LEXGO_BUDGET_START']); balance=money(os.environ['LEXGO_BUDGET_BALANCE_USD']); monthly=money(os.getenv('LEXGO_MONTHLY_DEBIT_USD') or '1.0')
    gh=GitHub(); r=calculate(kind,today,start,balance,monthly,gh.records(RES,'reservation.json',start),gh.records(SET,'settlement.json',start),os.environ['GITHUB_RUN_ID'])
    save(path,r); print(json.dumps(r)); return r

def settle(reservation,usage,out):
    r=read_json(reservation)
    if not r['allowed']:return
    debit=r['reserved_usd']; est=None
    try:
        u=read_json(usage); summary=read_json(Path(usage).with_name('run_summary.json'))
        if (u['publication_allowed'] is False and summary['publication_allowed'] is False and summary['simulated'] is False and summary['api_calls']==len(u['calls']) and money(summary['conservative_budget_debit_usd'])==money(u['conservative_budget_debit_usd'])):
            debit=money(u['conservative_budget_debit_usd']); est=money(u['estimated_usd'])
    except (OSError,ValueError,KeyError,TypeError):pass
    save(out,{'run_id':r['run_id'],'date':r['date'],'kind':r['kind'],'debit_usd':debit,'estimated_cost_usd':est,'publication_allowed':False})

def find_json(z,suffix):
    names=[n for n in z.namelist() if n==suffix or n.endswith('/'+suffix)]
    if len(names)!=1: raise ValueError('Expected exactly one '+suffix)
    return json.loads(z.read(names[0]))

def collect_daily(gh,day):
    records=[]
    for art in sorted(gh.list(DAILY),key=lambda a:a['created_at'],reverse=True):
        d=madrid_day(art['created_at'])
        if not day-timedelta(days=6)<=d<=day or art.get('expired'):continue
        with gh.archive(art) as z:
            try:
                s=find_json(z,'seo_v50/article/run_summary.json')
                if s['result']!='REVIEW_READY' or s['simulated'] is not False or s['publication_allowed'] is not False:continue
                topic=s['topics_attempted'][-1]; prefix='seo_v50/article/'+topic['artifact_directory']+'/'
                a=find_json(z,prefix+'article.json'); m=find_json(z,prefix+'article_metadata.json'); ev=find_json(z,prefix+'evidence.json'); review=find_json(z,prefix+'legal_review.json')
                if a['content_hash']!=review['article_hash'] or review['passed'] is not True:continue
                cat=m['category']; gate=renewal.assess(a['title'])
                if gate['excluded'] or gate['business_category']!=cat:continue
                refs=sorted({(x['source_id'],int(x['article'])) for x in ev if x.get('source_id') in (engine.RD,engine.LO) and str(x.get('article','')).isdigit()})
                records.append({'date':d.isoformat(),'run_id':str(art['workflow_run']['id']),'category':cat,'topic':a['title'],'origin':m.get('origin'),'queries':m.get('queries',[]),'search_demand_evidence':m.get('search_demand_evidence'),'keyword_planner_estimate':m.get('keyword_planner_estimate'),'article_refs':[{'document':doc,'article':n} for doc,n in refs],'article_hash':a['content_hash']})
            except (KeyError,TypeError,ValueError):continue
    unique={}
    for r in records:unique.setdefault(r['article_hash'],r)
    return list(unique.values())

def choose_weekly(records,existing=(),prior_topics=()):
    def score(cat):
        rows=[r for r in records if r['category']==cat]
        return (sum(1 for r in rows if r.get('search_demand_evidence') or r.get('keyword_planner_estimate')),len(rows))
    for cat in sorted({r['category'] for r in records if r['category'] in TITLES},key=lambda c:(score(c),c),reverse=True):
        base=TITLES[cat].split(':',1)[0]
        alternatives=[TITLES[cat],base+': situaciones que conviene revisar antes de que caduque la autorización',base+': errores que debes evitar y efectos de presentar la solicitud']
        for title in alternatives:
            gate=renewal.assess(title)
            if gate['excluded'] or gate['business_category']!=cat:continue
            if renewal.policy.norm(title) in {renewal.policy.norm(t) for t in prior_topics}:continue
            dup,_,_=seo.classify_duplicate({'proposed_title':title,'primary_query':title},existing)
            if dup:continue
            rows=[r for r in records if r['category']==cat]
            return {'category':cat,'title':title,'research_history':rows,'topic_origin':'EDITORIAL_SYNTHESIS','search_demand_verified':False,'selection_reason':'Coherent weekly synthesis of archived daily research; not a measured keyword for this title','publication_allowed':False}
    return None

def weekly_plan(out):
    gh=GitHub(); records=collect_daily(gh,local_today()); prior=[]
    for a in gh.list(WEEKLY):
        if a.get('expired'):continue
        with gh.archive(a) as z:
            try:
                s=find_json(z,'article/run_summary.json')
                if s['result']=='REVIEW_READY':prior.extend(x['topic'] for x in s['topics_attempted'] if x['result']=='REVIEW_READY')
            except (KeyError,ValueError):continue
    p=choose_weekly(records,seo.metadata_inventory(Path(__file__).resolve().parents[1]),prior)
    upcoming=[]; day=local_today()
    if p:upcoming.append({'category':p['category'],'topic':p['title'],'status':'RESEARCH_SELECTED'})
    for cat,title in TITLES.items():
        if title in prior or (p and p['category']==cat):continue
        upcoming.append({'category':cat,'topic':title,'status':'PROVISIONAL_NOT_RESEARCHED'})
    calendar=[{'week':slot('weekly',day+timedelta(days=7*i)),**x} for i,x in enumerate(upcoming[:6])]
    save(out,{'selected':p,'daily_research':records,'prior_weekly_topics':prior,'weekly_calendar':calendar,'publication_allowed':False});return p

def weekly_run(plan,reservation,output):
    p=read_json(plan)['selected'];r=read_json(reservation)
    if not p or not r['allowed']:return 0
    result=engine.run(output,category=p['category'],topic=p['title'],article_type='information',bootstrap=False,limits=engine.Limits(topics=1,research_rounds=2,draft_repairs=1,usd=r['reserved_usd']),website_root=Path(__file__).resolve().parents[1],weekly_context=p['research_history'])
    return 0 if result['result']=='REVIEW_READY' else 2

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('reserve');a.add_argument('kind',choices=CAPS);a.add_argument('path')
    a=sub.add_parser('settle');a.add_argument('reservation');a.add_argument('usage');a.add_argument('output')
    a=sub.add_parser('weekly-plan');a.add_argument('output')
    a=sub.add_parser('weekly-run');a.add_argument('plan');a.add_argument('reservation');a.add_argument('output')
    a=p.parse_args()
    if a.cmd=='reserve':prepare(a.kind,a.path)
    elif a.cmd=='settle':settle(a.reservation,a.usage,a.output)
    elif a.cmd=='weekly-plan':weekly_plan(a.output)
    else:return weekly_run(a.plan,a.reservation,a.output)
    return 0
if __name__=='__main__':sys.exit(main())
