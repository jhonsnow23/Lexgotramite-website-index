"""Up to three bounded alternative editorial proposals, independently reviewed.
Does not modify the original research or certify legal correctness.
"""
import json
try:
    from evidence_passages_v50 import build_catalog, resolve_passage, select_context, short_passage_context
    from temporary_residence_policy_v50 import classify, norm, SEEDS
except ImportError:
    from scripts.evidence_passages_v50 import build_catalog, resolve_passage, select_context, short_passage_context
    from scripts.temporary_residence_policy_v50 import classify, norm, SEEDS


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


def commercial_scope_check(plan, proposal):
    """Context may clarify an ambiguous title, never override explicit exclusions."""
    original=plan.get('commercial_classification', {})
    cat=original.get('business_category')
    title=classify(proposal['title'])
    intent=classify(proposal['search_intent'])
    context=classify(proposal['title']+' — '+proposal['search_intent'])
    hard=lambda c: c['excluded'] and c['exclusion_reason']!='AMBIGUOUS_OR_OUT_OF_SCOPE'
    conflict=lambda c: not c['excluded'] and c['business_category']!=cat
    # Do not use original queries to inject a category into an unrelated title.
    # Ambiguous titles need a same-category intent and a continuity procedure.
    procedure=any(w in norm(proposal['title']).split() for w in
                  ('modificacion','modificar','prorroga','prorrogar','renovacion','renovar','continuidad','continuar'))
    # In the regularisation category, cuenta ajena/propia can describe the
    # destination rather than the origin. Require an explicit matching title
    # and a matching combined classification to distinguish those roles.
    destination_intent=(cat=='regularizacion_2026' and title['business_category']==cat
                        and intent['business_category'] in ('cuenta_ajena','cuenta_propia')
                        and context['business_category']==cat)
    subject=any(w in norm(proposal['title']).split() for w in
                ('residencia','autorizacion','191','arraigo'))
    accepted=(cat in SEEDS and not original.get('excluded') and proposal['business_category']==cat
              and not any(hard(c) for c in (title,intent,context))
              and not conflict(title) and not conflict(context)
              and (not conflict(intent) or destination_intent)
              and (title['business_category']==cat or
                   (procedure and subject and intent['business_category']==cat and context['business_category']==cat)))
    return {'original_category':cat,'original_search_intent':original.get('search_intent'),
            'proposed_category':proposal['business_category'],'proposed_search_intent':proposal['search_intent'],
            'title_classification':title,'intent_classification':intent,'context_classification':context,
            'accepted':accepted}


def selectable_routes(dossier):
    return {r['route_id'] for r in dossier.get('procedure_context',{}).get('routes',[])
            if not str(r.get('verification_status','')).startswith(('UNRESOLVED','EXCLUDED'))
            and not str(r.get('applicability_to_DA20_DA21','')).startswith('NOT_APPLICABLE')}


def alternative_scope(plan, covered, evidence, dossier, *, call, model, client, report, max_proposals=3):
    """Retry substantive rejections only; never retry transport/integrity failures blindly."""
    max_proposals=max(1,min(3,max_proposals))
    attempts=[]; feedback=[]
    for _ in range(max_proposals):
        current={}
        result=_one_scope(plan,covered,evidence,dossier,call=call,model=model,client=client,report=current,feedback=feedback)
        attempts.append(current)
        report.clear()
        report.update(current)
        report.update(max_proposals=max_proposals,attempts=attempts)
        if result is not None: return result
        reason=current.get('reason')
        if reason not in ('COMMERCIAL_SCOPE_CHANGED','FORBIDDEN_ROUTE_IDS','INDEPENDENT_SCOPE_REJECTED','TITLE_NOT_NARROWED','ORIGINAL_BLOCKING_GAPS_NOT_ACCOUNTED_FOR','MISSING_TITLE','REPEATED_PROPOSAL'):
            break
        feedback.append({'reason':reason,'title':(current.get('proposal') or {}).get('title') if isinstance(current.get('proposal'),dict) else None,
                         'scope':(current.get('proposal') or {}).get('scope') if isinstance(current.get('proposal'),dict) else None,
                         'forbidden_route_ids':current.get('forbidden_route_ids',[]),
                         'review':current.get('independent_scope_review')})
    return None


def _one_scope(plan, covered, evidence, dossier, *, call, model, client, report, feedback):
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
    alias_map, short_selected=short_passage_context(selected)
    report['passage_alias_map']=alias_map
    route_set=selectable_routes(dossier)
    report['selectable_route_ids']=sorted(route_set)
    if not route_set:
        report['status']='NO_SELECTABLE_ROUTES'; return None
    proposal_fields={**PROPOSAL_FIELDS,'business_category':{'type':'string','enum':[plan['commercial_classification']['business_category']]},'questions':{**PROPOSAL_FIELDS['questions'],'items':{**PROPOSAL_FIELDS['questions']['items'],'properties':{**CLAIM_FIELDS,'passage_ids':{'type':'array','items':{'type':'string','enum':list(alias_map)}},'route_ids':{'type':'array','items':{'type':'string','enum':sorted(route_set)}}}}}}
    data={'original_plan':plan,'original_coverage':covered,'blocking_gaps':gaps,'official_passages':short_selected,'dossier':dossier,'selectable_route_ids':sorted(route_set),'previous_rejections':feedback}
    def ask(name, fields, prompt, payload):
        trace={}; report[name+'_transport']=trace
        result=call([{'role':'system','content':prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
                    model=model,client=client,response_format=schema(name,fields),diagnostics=trace)
        report[name]=result
        return result
    try:
        proposal=ask('proposal',proposal_fields,
            'Propose ONE narrower Spanish article, or empty title if none. Same commercial category and genuine search intent. '
            'If previous_rejections is nonempty, propose a genuinely different, narrower scope that addresses the recorded rejection. Prefer a single verified route or a clearly bounded subtopic; do not repeat the original broad modification-and-extension guide under a new title. '
            'Select only the passages necessary for each answer, including controlling exceptions; do not cite ranges of aliases in prose or select the whole catalog. '
            'Do not solve or erase original gaps. Every essential question needs an explicit supported answer with exact short passage aliases (P001 etc.) and applicable route IDs. '
            'Use only selectable route IDs; never include an unresolved or excluded branch even if you list it as a limitation. Do not infer unavailable routes or exceptional eligibility from uncertainty. Include all material conditions, exceptions, deadlines and effects needed for the specific article. '
            'Explicitly list each original blocking gap ID outside the new scope, and limitations and individual conditions. No exhaustive title for a partial guide.',data)
        if not isinstance(proposal,dict): raise ValueError('INVALID_PROPOSAL')
        for key in ('title','search_intent','scope','utility','seo_rationale','omission_rationale','business_category'):
            if not isinstance(proposal.get(key),str) or not proposal[key].strip(): raise ValueError('MISSING_'+key.upper())
        if any(norm(f.get('title') or '')==norm(proposal['title']) and norm(f.get('scope') or '')==norm(proposal['scope']) for f in feedback):
            raise ValueError('REPEATED_PROPOSAL')
        for key in ('limitations','individual_conditions','excluded_gap_ids'):
            if not isinstance(proposal.get(key),list) or any(not isinstance(v,str) or not v.strip() for v in proposal[key]): raise ValueError('INVALID_'+key.upper())
        if not proposal['limitations']: raise ValueError('MISSING_LIMITATIONS')
        if set(proposal['excluded_gap_ids'])!={g['gap_id'] for g in gaps}: raise ValueError('ORIGINAL_BLOCKING_GAPS_NOT_ACCOUNTED_FOR')
        report['commercial_scope_check']=commercial_scope_check(plan,proposal)
        if not report['commercial_scope_check']['accepted']:
            raise ValueError('COMMERCIAL_SCOPE_CHANGED')
        if proposal['title'].strip().casefold()==plan['topic'].strip().casefold(): raise ValueError('TITLE_NOT_NARROWED')
        questions=proposal.get('questions'); sent=set(report['passages_sent']); records={p['passage_id']:p for p in selected}
        if not isinstance(questions,list) or not 2<=len(questions)<=8: raise ValueError('INVALID_QUESTION_COUNT')
        alt_questions=[]; seen=set(); resolved_questions=[]
        for i,q in enumerate(questions):
            if not isinstance(q,dict) or any(not isinstance(q.get(k),str) or not q[k].strip() for k in ('question','answer')): raise ValueError('INVALID_QUESTION')
            if q['question'].strip().casefold() in seen: raise ValueError('DUPLICATE_QUESTION')
            seen.add(q['question'].strip().casefold())
            refs=q.get('passage_ids'); routes=q.get('route_ids')
            if not isinstance(refs,list) or not refs or any(not isinstance(p,str) for p in refs) or len(set(refs))!=len(refs): raise ValueError('INVALID_PASSAGE_IDS')
            if not isinstance(routes,list) or not routes or any(not isinstance(r,str) for r in routes) or len(set(routes))!=len(routes): raise ValueError('INVALID_ROUTE_IDS')
            forbidden=sorted(set(routes)-route_set)
            if forbidden:
                report['forbidden_route_ids']=forbidden
                report['forbidden_route_question_index']=i
                raise ValueError('FORBIDDEN_ROUTE_IDS')
            resolved=[]
            canonical_refs=[alias_map.get(pid,pid) for pid in refs]
            if len(set(canonical_refs))!=len(canonical_refs): raise ValueError('DUPLICATE_PASSAGE_IDS')
            for pid in canonical_refs:
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
            'Compare original and proposed substantive scope, not just titles. Reject a broad guide that still depends on the unresolved branch, even if a limitation is stated. '
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
