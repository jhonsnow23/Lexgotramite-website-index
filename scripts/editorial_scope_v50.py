"""One bounded alternative editorial proposal, independently reviewed.
Does not modify the original research or certify legal correctness.
"""
import json
try:
    from evidence_passages_v50 import build_catalog, resolve_passage, select_context
    from temporary_residence_policy_v50 import classify
except ImportError:
    from scripts.evidence_passages_v50 import build_catalog, resolve_passage, select_context
    from scripts.temporary_residence_policy_v50 import classify


def schema(name, fields):
    return {'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':{
        'type':'object','additionalProperties':False,'required':list(fields),'properties':fields}}}

STR={'type':'string'}
STRS={'type':'array','items':STR}
CLAIM_FIELDS={'question':STR,'answer':STR,'passage_ids':STRS,'route_ids':STRS}
PROPOSAL_FIELDS={'title':STR,'search_intent':STR,'business_category':STR,'scope':STR,
    'questions':{'type':'array','items':{'type':'object','additionalProperties':False,'required':list(CLAIM_FIELDS),'properties':CLAIM_FIELDS}},
    'excluded_gap_ids':STRS,'limitations':STRS,'individual_conditions':STRS,'utility':STR,'seo_rationale':STR,'omission_rationale':STR}
REVIEW_FIELDS={'approved':{'type':'boolean'},'all_essential_questions_covered':{'type':'boolean'},
    'no_misleading_omissions':{'type':'boolean'},'intent_and_category_preserved':{'type':'boolean'},
    'title_matches_scope':{'type':'boolean'},'supported_question_indices':{'type':'array','items':{'type':'integer'}},'reasons':STRS}


def alternative_scope(plan, covered, evidence, dossier, *, call, model, client, report):
    report.update({'status':'NOT_APPROVED','original_scope':plan,'original_coverage':covered,'publication_allowed':False,'max_proposals':1})
    gaps=[]
    for q in covered:
        for i,fact in enumerate(q.get('blocking_missing_facts') or []):
            gaps.append({'gap_id':f"{q['id']}:{i}",'question_id':q['id'],'fact':fact})
    report['original_blocking_gaps']=gaps
    # Only a genuine recorded material legal gap triggers this path, not API,
    # malformed-response, integrity or retrieval errors alone.
    material=any(a.get('classification')=='MATERIAL' for q in covered for a in q.get('gap_assessments',[]))
    # Other commercial categories use the existing conservative coverage gate,
    # not the regularisation-specific gap classifier. A concrete unresolved
    # legal question can be considered, but never a retrieval/format failure.
    if plan.get('commercial_classification',{}).get('business_category') != 'regularizacion_2026':
        material=any(q.get('status') in ('PARTIALLY_ANSWERED','REQUIRES_LEGAL_INTERPRETATION') and q.get('missing_facts') and q.get('evidence_ids') for q in covered)
    if not gaps or not material:
        report['status']='NO_RECORDED_MATERIAL_GAP'; return None
    catalog=build_catalog(evidence); selected, omitted=select_context(catalog,evidence,dossier)
    report['passages_sent']=[p['passage_id'] for p in selected]; report['passages_omitted_for_budget']=omitted
    if not selected or any(not catalog['passages'][p]['parent_passage_id'] for p in omitted):
        report['status']='INSUFFICIENT_CONTEXT'; return None
    data={'original_plan':plan,'original_coverage':covered,'blocking_gaps':gaps,'official_passages':selected,'dossier':dossier}
    def ask(name, fields, prompt, payload):
        trace={}; report[name+'_transport']=trace
        result=call([{'role':'system','content':prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
                    model=model,client=client,response_format=schema(name,fields),diagnostics=trace)
        report[name]=result
        return result
    try:
        proposal=ask('proposal',PROPOSAL_FIELDS,
            'Propose ONE narrower Spanish article, or empty title if none. Same commercial category and genuine search intent. '
            'Do not solve or erase original gaps. Every essential question needs an explicit supported answer with official passage IDs and applicable route IDs. '
            'Do not infer unavailable routes or exceptional eligibility from uncertainty. Include all material conditions, exceptions, deadlines and effects needed for the specific article. '
            'Explicitly list each original blocking gap ID outside the new scope, and limitations and individual conditions. No exhaustive title for a partial guide.',data)
        if not isinstance(proposal,dict): raise ValueError('INVALID_PROPOSAL')
        for key in ('title','search_intent','scope','utility','seo_rationale','omission_rationale','business_category'):
            if not isinstance(proposal.get(key),str) or not proposal[key].strip(): raise ValueError('MISSING_'+key.upper())
        for key in ('limitations','individual_conditions','excluded_gap_ids'):
            if not isinstance(proposal.get(key),list) or any(not isinstance(v,str) or not v.strip() for v in proposal[key]): raise ValueError('INVALID_'+key.upper())
        if not proposal['limitations']: raise ValueError('MISSING_LIMITATIONS')
        if set(proposal['excluded_gap_ids'])!={g['gap_id'] for g in gaps}: raise ValueError('ORIGINAL_BLOCKING_GAPS_NOT_ACCOUNTED_FOR')
        cat=plan['commercial_classification']['business_category']
        classification=classify(proposal['title'])
        if classification['excluded'] or classification['business_category']!=cat or proposal['business_category']!=cat:
            raise ValueError('COMMERCIAL_SCOPE_CHANGED')
        if proposal['title'].strip().casefold()==plan['topic'].strip().casefold(): raise ValueError('TITLE_NOT_NARROWED')
        questions=proposal.get('questions'); sent=set(report['passages_sent']); records={p['passage_id']:p for p in selected}
        if not isinstance(questions,list) or not 2<=len(questions)<=8: raise ValueError('INVALID_QUESTION_COUNT')
        alt_questions=[]; seen=set(); resolved_questions=[]
        route_set={r['route_id'] for r in dossier.get('procedure_context',{}).get('routes',[])}
        for i,q in enumerate(questions):
            if not isinstance(q,dict) or any(not isinstance(q.get(k),str) or not q[k].strip() for k in ('question','answer')): raise ValueError('INVALID_QUESTION')
            if q['question'].strip().casefold() in seen: raise ValueError('DUPLICATE_QUESTION')
            seen.add(q['question'].strip().casefold())
            refs=q.get('passage_ids'); routes=q.get('route_ids')
            if not isinstance(refs,list) or not refs or any(not isinstance(p,str) for p in refs) or len(set(refs))!=len(refs): raise ValueError('INVALID_PASSAGE_IDS')
            if not isinstance(routes,list) or not routes or any(not isinstance(r,str) or r not in route_set for r in routes): raise ValueError('INVALID_ROUTE_IDS')
            resolved=[]
            for pid in refs:
                p=resolve_passage(pid,catalog,evidence,allowed_ids=sent)
                if not p: raise ValueError('INVALID_PASSAGE_ID')
                known_routes=set(records[pid]['route_ids'])
                if known_routes and not known_routes.intersection(routes): raise ValueError('PASSAGE_WRONG_ROUTE')
                resolved.append(p)
            eid=list(dict.fromkeys(p['evidence_id'] for p in resolved))
            alt_questions.append({'id':f'alt_{i+1}','question':q['question'],'query':q['question']})
            resolved_questions.append({'question_id':f'alt_{i+1}','answer':q['answer'],'evidence_ids':eid,'supporting_passages':resolved,'route_ids':routes})
        verdict=ask('independent_scope_review',REVIEW_FIELDS,
            'Independently audit the proposed NEW scope, not the old guide. Verify each answer against literal official text and applicable routes, all conditions, exceptions, filing rules and timing. '
            'Check every original blocking gap and reject if it remains material to the new article, or if omitting it misleads the reader. '
            'Never approve an assertion that an unresolved route does not exist, nor infer exceptional-extension eligibility. '
            'Reject trivial or SEO-irrelevant content, broad titles, incomplete answers, wrong branches and unsupported claims. '
            'Return all supported zero-based question indices, reasons, and explicit booleans. Approve only if every check passes.',
            {**data,'proposal':proposal,'resolved_questions':resolved_questions})
        if not isinstance(verdict,dict) or any(verdict.get(k) is not True for k in REVIEW_FIELDS if k not in ('supported_question_indices','reasons')):
            raise ValueError('INDEPENDENT_SCOPE_REJECTED')
        indices=verdict.get('supported_question_indices')
        if not isinstance(indices,list) or any(type(i) is not int for i in indices) or sorted(indices)!=list(range(len(questions))): raise ValueError('INCOMPLETE_INDEPENDENT_REVIEW')
        if not isinstance(verdict.get('reasons'),list) or not verdict['reasons'] or any(not isinstance(r,str) or not r.strip() for r in verdict['reasons']): raise ValueError('MISSING_REVIEW_REASON')
        # Separate alternative plan/coverage; original report remains intact.
        alt_plan={**plan,'topic':proposal['title'],'commercial_classification':{**plan['commercial_classification'],'search_intent':proposal['search_intent']},
                  'research_questions':alt_questions,'adaptive_editorial_scope':{'original_topic':plan['topic'],'scope':proposal['scope'],
                  'excluded_original_gaps':gaps,'limitations':proposal['limitations'],'individual_conditions':proposal['individual_conditions'],
                  'approved_answers':resolved_questions,'original_research_coverage_preserved':True}}
        alt_covered=[{**q,'status':'ANSWERED_WITH_EVIDENCE','evidence_ids':a['evidence_ids'],'missing_facts':[],
                      'reason':a['answer'],'draft_readiness':'READY_WITH_DECLARED_LIMITATIONS',
                      'supporting_passages':a['supporting_passages']} for q,a in zip(alt_questions,resolved_questions)]
        report.update({'status':'APPROVED_FOR_DRAFT_ONLY','authorized_plan':alt_plan,'alternative_coverage':alt_covered})
        return alt_plan,alt_covered
    except Exception as exc:
        # Diagnostics retain response/transport; no alternate draft on failure.
        report.update({'status':'REJECTED','reason':str(exc)[:300],'error_type':type(exc).__name__})
        return None
