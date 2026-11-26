"""Commercial query clusters built from observed query/page rows, no paid AI."""
import hashlib
import math
import re
from urllib.parse import urlsplit
try:
    from . import temporary_residence_policy_v50 as policy
except ImportError:
    import temporary_residence_policy_v50 as policy

STOP=set('de del la las el los en para por con una un y a al que se es su mi tu espana'.split())
EQUIV={'renovar':'renovacion','renovaciones':'renovacion','renueve':'renovacion','prorrogar':'prorroga','modificar':'modificacion','documentos':'documentacion','papeles':'documentacion','plazos':'plazo','cuando':'plazo','caducar':'caducidad','caduca':'caducidad','vencimiento':'caducidad'}


def signature(query):
    q=policy.norm(query); c=policy.classify(query)
    if c['excluded']:return None
    # Do not let initial regularisation or document-card searches enter continuity.
    if c['business_category']=='regularizacion_2026' and not re.search(r'\b(renov\w*|modific\w*|prorrog\w*|continu\w*)\b',q):return None
    if re.search(r'\b(tie|nie|huellas|duplicado|tarjeta)\b',q) and not re.search(r'\b(autorizacion|permiso|residencia)\b',q):return None
    words={EQUIV.get(w,w) for w in q.split() if w not in STOP}
    # Only normalize a narrow, explicit equivalence: renewal timing before expiry.
    # Preserve 'después', 'tarde', amounts, subtypes, employer changes, etc.
    if {'renovacion','plazo'}<=words and 'antes' in words and 'caducidad' in words:
        words-={'antes','caducidad'}
        # Do not merge explicit before-expiry with general timing: preserve qualifier.
        words.add('antes_caducidad')
    key=c['business_category']+'|'+','.join(sorted(words))
    return c['business_category'],'gsc_'+hashlib.sha256(key.encode()).hexdigest()[:20]


def cluster_windows(windows, discard=lambda q:None):
    result={}
    for window in ('7','28','90'):
        if window not in windows:continue
        grouped={}
        for row in windows[window]:
            keys=row.get('keys',[])
            if not keys or not isinstance(keys[0],str) or discard(keys[0]):continue
            query=keys[0].strip(); sig=signature(query)
            if not sig:continue
            try:
                i=int(row['impressions']);c=int(row['clicks']);p=float(row['position'])
                if i<=0 or not 0<=c<=i or not math.isfinite(p) or p<=0:continue
            except (ValueError,TypeError,KeyError):continue
            cat,cid=sig; cluster=grouped.setdefault(cid,{'id':cid,'category':cat,'queries':{},'impressions':0,'clicks':0,'weighted_position':0,'pages':set()})
            # Keep each actual query spelling and its metrics, rather than inventing demand for the title.
            q=cluster['queries'].setdefault(query,{'query':query,'impressions':0,'clicks':0,'weighted_position':0,'pages':set()})
            for x in (cluster,q):
                x['impressions']+=i;x['clicks']+=c;x['weighted_position']+=i*p
                if len(keys)>1 and isinstance(keys[1],str):x['pages'].add(keys[1])
        def finish(x):
            x['average_position']=round(x.pop('weighted_position')/x['impressions'],2);x['ctr']=x['clicks']/x['impressions'];x['landing_pages']=sorted(x.pop('pages'));return x
        result[window]=[]
        for g in grouped.values():
            g['queries']=sorted([finish(q) for q in g['queries'].values()],key=lambda q:(-q['impressions'],q['query']))
            result[window].append(finish(g))
        result[window].sort(key=lambda g:(-g['impressions'],g['id']))
    return result


def rank(windows):
    maps={w:{g['id']:g for g in groups} for w,groups in windows.items()}
    rows=[]
    for cid in sorted(set(maps.get('28',{}))|set(maps.get('90',{}))):
        a=maps.get('28',{}).get(cid); b=maps.get('90',{}).get(cid); base=a or b
        metrics={w:maps.get(w,{}).get(cid) for w in ('7','28','90')}
        imp28=a['impressions'] if a else 0; imp90=b['impressions'] if b else 0
        primary=base['queries'][0]['query']; queries=list(dict.fromkeys(q['query'] for x in (a,b) if x for q in x['queries']))
        pos=base['average_position'];ctr=base['ctr']
        # Heuristic, not forecast: overlapping windows are never added.
        breakdown={'observed_demand':round(min(35,7*math.log1p(max(imp28,imp90))),2),
                   'ranking_opportunity':20 if 4<=pos<=20 else 10 if pos<=50 else 3,
                   'low_ctr_signal':5 if pos<=20 and ctr<.03 else 0,
                   'recent_demand_signal':5 if a and b and imp28/28>imp90/90*1.25 else 0}
        rows.append({'cluster_id':cid,'proposed_title':primary[:1].upper()+primary[1:], 'primary_query':primary,'supporting_queries':queries,
                     'impressions_28d':imp28,'impressions_90d':imp90,'clicks_28d':a['clicks'] if a else 0,'average_position_28d':a['average_position'] if a else None,
                     'existing_pages':sorted(set(urlsplit(u).path.lstrip('/') for x in (a,b) if x for u in x['landing_pages'] if urlsplit(u).hostname in ('lexgotramite.com','www.lexgotramite.com'))),
                     'observed_metrics':metrics,'score_breakdown':breakdown,'score':sum(breakdown.values())})
    return sorted(rows,key=lambda x:(-x['score'],x['cluster_id']))


def verified_proposal(row):
    """Check observed-query provenance, not simply positive numbers or an origin label."""
    if row.get('topic_origin') not in ('GSC_VERIFIED_OPPORTUNITY','GSC_QUERY_CLUSTER') or row.get('search_demand_verified') is not True:return False
    try:
        d=row['search_demand_evidence'];meta=d['source_metadata'];windows=d['observed_windows'];qs=set(row['queries'])
        if meta['source']!='google_search_console_api' or meta['verified_google_data'] is not True:return False
        found=set();positive=False
        for w in ('28','90'):
            record=windows.get(w); expected=d['impressions_'+w+'d']
            if record is None:
                if expected!=0:return False
                continue
            if record['id']!=row['cluster_id'] or record['impressions']!=expected or type(expected) is not int or expected<=0:return False
            if sum(q['impressions'] for q in record['queries'])!=expected:return False
            for q in record['queries']:
                if signature(q['query'])!=(record['category'],record['id']) or q['query'] not in qs:return False
                found.add(q['query'])
            positive=True
        return positive and found==qs and row['primary_query'] in found
    except (KeyError,ValueError,TypeError,AttributeError):return False
