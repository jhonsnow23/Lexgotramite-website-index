#!/usr/bin/env python3
"""Search-demand-driven SEO decision layer for Lex Go Trámite.

Inputs: real GSC v2 report, website's existing HTML, 60-day history carried through
GitHub Actions artifacts. Outputs: ranked opportunities, 30-day editorial calendar,
selection for the existing v4.1 generator. This script never publishes content.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import re
import unicodedata
import urllib.request
import zipfile
from io import BytesIO
from difflib import SequenceMatcher

PREFER = {
    'residence_renewal': ('Renovación de residencia', 'Renovar la residencia en España: trámites según autorización', 'residence_renewal'),
    'residency_options': ('Tipos de residencia legal', 'Tipos de residencia en España: cómo identificar la autorización adecuada', 'residency_options'),
    'regularization_processing': ('Plazos de regularización', 'Regularización: cómo consultar el estado del expediente', 'regularization_processing'),
    'long_term_residence': ('Residencia de larga duración', 'Residencia de larga duración: requisitos y trámites', 'long_term_residence'),
    'nationality_requirements': ('Requisitos para nacionalidad', 'Nacionalidad española por residencia: requisitos a verificar', 'nationality'),
    'nationality_documents': ('Documentación de nacionalidad', 'Documentos para solicitar la nacionalidad española por residencia', 'nationality'),
    'regularization_other': ('Regularización y arraigo', 'Cómo identificar opciones oficiales de regularización', 'regularization_processing'),
    'residency_other': ('Estancia y residencia', 'Estancia y residencia en España: diferencias y trámites', 'residency_options'),
}
# Exact semantic intents; prevent superficially similar queries from being legally conflated.
EXISTING = {
    'residence_renewal':['blog/renovar-residencia-espana.html'],
    'residency_options':['blog/tipos-de-residencia-en-espana.html'],
    'regularization_processing':['blog/cuanto-tarda-proceso-regularizacion-espana.html','blog/cuanto-tarda-la-regularizacion-en-espana.html'],
    'long_term_residence':['blog/renovar-residencia-espana.html'],
    'nationality_requirements':['nacionalidad-espanola.html'],
    'nationality_documents':['nacionalidad-espanola.html'],
    'regularization_other':['regularizacion-espana-2026.html'],
    'residency_other':['blog/residencia-por-estudios-espana.html','residencia-espana.html'],
}
# Source availability is a gate for generation, not proof of legal correctness.
V41_AVAILABLE={'residence_renewal','residency_options','long_term_residence','nationality_requirements','nationality_documents','residency_other'}


def normalized(s):
    s=unicodedata.normalize('NFKD',str(s).lower())
    return re.sub(r'[^a-z0-9 ]+',' ',''.join(c for c in s if not unicodedata.combining(c))).strip()


def validate_report(rep):
    if rep.get('metadata',{}).get('source')!='google_search_console_api' or rep.get('metadata',{}).get('verified_google_data') is not True:
        raise ValueError('Expected a real GSC report; fabricated or example data is blocked')
    if not isinstance(rep.get('windows',{}).get('28'),list):raise ValueError('Missing 28-day GSC clusters')
    return rep


def services_index(catalog):
    idx={}
    for s in catalog['services']:
        if not s['offered']:continue
        for x in s['intents']:
            if x in idx:raise ValueError('Ambiguous service catalog intent '+x)
            idx[x]=s
    return idx


def prior_history(history):
    if not history:return []
    if isinstance(history,dict):return history.get('events',[])
    return history


def in_cooldown(cluster,history,on,days=60):
    for h in prior_history(history):
        if h.get('cluster_id')!=cluster:continue
        try:d=date.fromisoformat(h['selected_on'])
        except (ValueError,KeyError,TypeError):continue
        if 0 <= (on-d).days < days and not h.get('material_legal_change_verified',False):return True
    return False


def matching_pages(root,cluster,queries):
    """Prefer known intent-specific pages; never assume arbitrary token overlap is legal equivalence."""
    root=Path(root)
    mapped=[p for p in EXISTING.get(cluster,[]) if (root/p).is_file()]
    if mapped:return mapped
    # If snapshot doesn't have mapped files, inspect other indexed HTML titles only as a low-certainty hint.
    tokens=set(normalized(' '.join(queries[:3])).split())-{'de','la','en','para','espana','del','el','y','por','como'}
    matches=[]
    for p in root.glob('blog/*.html'):
        slug=set(normalized(p.stem.replace('-',' ')).split())
        score=len(tokens & slug)/max(len(tokens),1)
        if score>=.75 and len(tokens & slug)>=2:matches.append(p.relative_to(root).as_posix())
    return sorted(matches)[:3]


def rank(rep,catalog,root,history,on=None):
    on=on or date.today()
    idx=services_index(catalog)
    w28={c['id']:c for c in rep['windows']['28']}
    w90={c['id']:c for c in rep['windows'].get('90',[])}
    items=[]
    for cid,c in w28.items():
        service=idx.get(cid)
        if not service or cid not in PREFER:continue
        n90=w90.get(cid,{})
        imp28=int(c.get('impressions',0));imp90=int(n90.get('impressions',0))
        # Uses measured impressions only; 90d and 28d metrics are overlapping, not summed.
        if max(imp28,imp90)<1:continue
        pages=matching_pages(root,cid,[q['query'] for q in c.get('representative_queries',[])])
        demand=min(30,round(7*math.log1p(imp90)))
        rankpos=float(c.get('average_position') or n90.get('average_position') or 100)
        if rankpos<=3:position=3
        elif rankpos<=20:position=23
        elif rankpos<=50:position=16
        elif rankpos<=80:position=10
        else:position=5
        relevance=20 if service['priority']==1 else 12
        gap=8 if not pages else 5
        trend=5 if imp28*3>imp90 else 0
        repeated_cluster=in_cooldown(cid,history,on)
        recently_selected_page=any(h.get('existing_page') and h.get('existing_page') in pages and 0 <= (on-date.fromisoformat(h['selected_on'])).days < 30 for h in prior_history(history) if h.get('selected_on'))
        penalty=50 if repeated_cluster or recently_selected_page else 0
        total=max(0,demand+position+relevance+gap+trend-penalty)
        title=PREFER[cid][1]
        queries=c.get('representative_queries',[])
        primary=max(queries,key=lambda x:x.get('impressions',0))['query'] if queries else cid
        action='MONITOR' if penalty or (imp28<3 and imp90<30) else ('IMPROVE_EXISTING_ARTICLE' if pages else 'CREATE_NEW_ARTICLE')
        if cid not in V41_AVAILABLE and action not in ('MONITOR','SKIP'):
            action='MONITOR'  # insufficient identified primary legal sources for the existing v4.1 generator
        items.append({
            'cluster_id':cid,'cluster_label':PREFER[cid][0],'proposed_title':title,
            'primary_query':primary,'supporting_queries':[q['query'] for q in queries],
            'service_id':service['id'],'service_name':service['name'],'service_landing_page':service['landing_page'],
            'demand_source':'Google Search Console (verified property impressions)',
            'impressions_7d':next((int(a.get('impressions',0)) for a in rep['windows'].get('7',[]) if a['id']==cid),0),
            'impressions_28d':imp28,'impressions_90d':imp90,
            'clicks_28d':int(c.get('clicks',0)),'average_position_28d':rankpos,
            'existing_pages':pages,'recommended_action':action,'cooldown_active':bool(penalty),
            'v41_evidence_coverage_candidate':cid in V41_AVAILABLE,
            'score':total,'score_breakdown':{'measured_demand':demand,'ranking_opportunity':position,'service_relevance':relevance,'content_gap':gap,'trend':trend,'cooldown_penalty':penalty},
            'reason':('Existing content should be improved' if pages else 'Candidate gap; requires coverage verification') + ('; 60-day cooldown active' if penalty else '') + ('; v4.1 legal-source scope insufficient' if cid not in V41_AVAILABLE else '')
        })
    return sorted(items,key=lambda x:(-x['score'],-x['impressions_90d'],x['cluster_id']))


def plan(items,on,history,slots=12):
    """Schedule <=3 distinct, eligible opportunities in a rolling 30-day period.
    More slots remain empty; no forced article quotas and no duplicate clusters.
    """
    eligible=[i for i in items if i['recommended_action'] not in ('MONITOR','SKIP') and not i['cooldown_active']]
    selected=[];selected_services=set();used_pages=set()
    def add(x):
        if x['cluster_id'] in {y['cluster_id'] for y in selected}:return
        if x['existing_pages'] and set(x['existing_pages']) & used_pages:return
        selected.append(x);used_pages.update(x['existing_pages']);selected_services.add(x['service_id'])
    for x in eligible:
        if x['service_id'] not in selected_services:add(x)
    for x in eligible:add(x)
    dates=[]
    for offset in range(30):
        day=on+timedelta(days=offset)
        if day.weekday() in (0,2,4):dates.append(day)
    calendar=[]
    for day,x in zip(dates[:slots],selected):
        calendar.append({'planned_date':day.isoformat(),'cluster_id':x['cluster_id'],
           'search_query':x['primary_query'],'service':x['service_name'],
           'title':x['proposed_title'],'existing_page':x['existing_pages'][0] if x['existing_pages'] else None,
           'action':x['recommended_action'],'score':x['score'],'status':'DRAFT_CANDIDATE_NOT_APPROVED',
           'measured_impressions_28d':x['impressions_28d']})
    return calendar


def select_for_v41(items,history,on):
    # Same service-diversity order as the calendar, while still honoring the highest ranked new opportunity.
    for x in items:
        if x['recommended_action'] in ('MONITOR','SKIP') or x['cooldown_active'] or not x['v41_evidence_coverage_candidate']:continue
        cluster_id=PREFER[x['cluster_id']][2]
        return x,{'version':3,'proposals':[{'cluster_id':cluster_id,'action':'improve_existing_page',
           'proposed_title':x['proposed_title'],'queries':x['supporting_queries'],
           'sections_to_research':[x['primary_query']], 'origin_cluster_id':x['cluster_id'],
           'search_demand_evidence':{'impressions_28d':x['impressions_28d'],'impressions_90d':x['impressions_90d']}}]}
    return None,None


def load_prior_artifact():
    """Read the latest saved history from GitHub Actions artifacts (never requires repo write)."""
    repo=os.getenv('GITHUB_REPOSITORY','')
    token=os.getenv('GH_HISTORY_TOKEN','')
    if not repo or not token or not re.fullmatch(r'[\w.-]+/[\w.-]+',repo):return [],'No GitHub artifact credentials; manual/test mode'
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'lexgo-v42'}
    def get(url):
        req=urllib.request.Request(url,headers=headers)
        with urllib.request.urlopen(req,timeout=25) as r:return r.read()
    try:
        url=f'https://api.github.com/repos/{repo}/actions/artifacts?name=lexgo-v42-results&per_page=100'
        artifacts=json.loads(get(url)).get('artifacts',[])
        for art in sorted(artifacts,key=lambda a:a.get('created_at',''),reverse=True):
            if art.get('expired'):continue
            blob=get(art['archive_download_url'])
            with zipfile.ZipFile(BytesIO(blob)) as z:
                names=[x for x in z.namelist() if x.endswith('history.json')]
                if names:
                    data=json.loads(z.read(names[0]))
                    return prior_history(data),'Restored selection history from workflow artifact'
        # On first v4.2 run, honor recent v4.1 drafts instead of selecting the same topic again.
        legacy_url=f'https://api.github.com/repos/{repo}/actions/artifacts?name=lexgotramite-v41-draft-and-evidence&per_page=20'
        for art in sorted(json.loads(get(legacy_url)).get('artifacts',[]),key=lambda a:a.get('created_at',''),reverse=True):
            if art.get('expired'):continue
            with zipfile.ZipFile(BytesIO(get(art['archive_download_url']))) as z:
                candidates=[n for n in z.namelist() if n.endswith('decision.json')]
                for name in candidates:
                    decision=json.loads(z.read(name))
                    topic=normalized(decision.get('topic',''))
                    if 'renovar' in topic or 'renovacion' in topic:
                        return [{'selected_on':art['created_at'][:10],'cluster_id':'residence_renewal',
                                 'existing_page':'blog/renovar-residencia-espana.html',
                                 'source':'actual previous v4.1 artifact'}],'Imported previous v4.1 residence-renewal draft'
        return [],'No prior history artifact found' 
    except Exception as e:
        # Fail closed rather than lose cooldown protection when scheduled.
        raise RuntimeError('Cannot retrieve prior history safely: '+type(e).__name__) from e


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--report',default='reports/seo_intelligence.json')
    p.add_argument('--catalog',default='config/seo_v42_services.json')
    p.add_argument('--website-root',default='.')
    p.add_argument('--output',default='reports/seo_v42')
    p.add_argument('--history',default='')
    p.add_argument('--today',default='')
    p.add_argument('--require-history',action='store_true')
    args=p.parse_args(argv)
    rep=validate_report(json.loads(Path(args.report).read_text(encoding='utf8')))
    catalog=json.loads(Path(args.catalog).read_text(encoding='utf8'))
    on=date.fromisoformat(args.today) if args.today else date.today()
    if args.history:history=prior_history(json.loads(Path(args.history).read_text(encoding='utf8')));origin='provided history'
    else:history,origin=load_prior_artifact()
    if args.require_history and origin.startswith('No GitHub artifact credentials'):
        raise RuntimeError('History unavailable; refusing automated topic selection without 60-day cooldown state')
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    items=rank(rep,catalog,args.website_root,history,on)
    calendar=plan(items,on,history)
    selected,proposal=select_for_v41(items,history,on)
    (root/'ranked_opportunities.json').write_text(json.dumps({'source_metadata':rep['metadata'],'count':len(items),'opportunities':items},ensure_ascii=False,indent=2),encoding='utf8')
    (root/'editorial_calendar.json').write_text(json.dumps({'generated_on':on.isoformat(),'days':30,'entries':calendar,'unused_slots':max(0,12-len(calendar))},ensure_ascii=False,indent=2),encoding='utf8')
    status={'selected_on':on.isoformat(),'cluster_id':selected['cluster_id'],'service':selected['service_name'],'query':selected['primary_query'],'existing_page':selected['existing_pages'][0] if selected['existing_pages'] else None,'publication_allowed':False} if selected else None
    # This history records selection, not publication. A failed AI run still consumes a cooldown slot.
    history=history+([status] if status else [])
    (root/'history.json').write_text(json.dumps({'events':history[-200:],'updated_on':on.isoformat()},ensure_ascii=False,indent=2),encoding='utf8')
    (root/'selection.json').write_text(json.dumps({'selected':selected,'history_origin':origin,'publication_allowed':False,'selection_only':True},ensure_ascii=False,indent=2),encoding='utf8')
    if proposal:
        (root/'selected_v41_proposal.json').write_text(json.dumps(proposal,ensure_ascii=False,indent=2),encoding='utf8')
    summary=['# Lex Go Trámite v4.2 — search-demand editorial plan','',f'Report: {rep["metadata"].get("retrieved_at")} • GSC data through {rep["metadata"].get("data_end_date")}','',f'Unique eligible clusters observed: {len(items)}','', '|Priority|Intent|28d impressions|90d impressions|Service|Action|Score|','|---|---|---:|---:|---|---|---:|']
    for n,x in enumerate(items,1):summary.append(f'|{n}|{x["cluster_label"]}|{x["impressions_28d"]}|{x["impressions_90d"]}|{x["service_name"]}|{x["recommended_action"]}|{x["score"]}|')
    summary+=['','## Next editorial candidates','']
    for x in calendar[:3]:summary.append(f'- {x["planned_date"]}: {x["title"]} ({x["service"]})')
    summary+=['',f'Next AI draft: {selected["proposed_title"] if selected else "none eligible"}','', 'Safety: these are search insights, not validated legal claims. No publication occurs.']
    (root/'README.md').write_text('\n'.join(summary)+'\n',encoding='utf8')
    print(json.dumps({'eligible_clusters':len(items),'selected':status,'calendar_entries':len(calendar),'history_origin':origin},ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())
