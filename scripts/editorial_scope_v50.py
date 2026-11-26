"""Up to three bounded alternative editorial proposals, independently reviewed.
Does not modify the original research or certify legal correctness.
"""
import json
try:
    from evidence_passages_v50 import build_catalog, resolve_passage, select_context, short_passage_context
    from temporary_residence_policy_v50 import classify, norm, SEEDS, employer_change_focus
except ImportError:
    from scripts.evidence_passages_v50 import build_catalog, resolve_passage, select_context, short_passage_context
    from scripts.temporary_residence_policy_v50 import classify, norm, SEEDS, employer_change_focus


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


def scope_candidates(plan, dossier):
    """Select concrete conditional branches, not the umbrella procedure.
    A candidate is not a finding of eligibility or editorial sufficiency.
    """
    allowed = selectable_routes(dossier)
    if plan.get('commercial_classification', {}).get('business_category') == 'regularizacion_2026':
        # Prefer concrete modification branches; the exceptional extension is
        # dependent on inability to modify and still needs independent review.
        order = ('MOD_ART191_2_AJENA_LT_1Y', 'MOD_ART191_3_AJENA_GE_1Y',
                 'MOD_ART191_3_PROPIA_GE_1Y', 'PRORROGA_EXCEPCIONAL_1Y',
                 'PRORROGA_EXCEPCIONAL_4Y')
        return [r for r in order if r in allowed]
    return sorted(allowed)


def passage_route_compatibility(record, primary_route):
    """Shared DA20/21 modification rules are not a separate destination route.

    Only these identified provisions inherit to the three mapped work-enabled
    branches. This is citation eligibility, not proof of the proposed answer.
    The independent reviewer must still check the actual passage and claim.
    """
    routes=set(record.get('route_ids') or [])
    if primary_route in routes:
        return 'DIRECT_ROUTE'
    if (record.get('document_reference') == 'BOE-A-2026-8284'
            and record.get('article_reference') in ('DA20.10','DA21.10')
            and record.get('applicability') == 'CONDITIONALLY_APPLICABLE'
            and 'MODIFICACION_ART_191' in routes
            and primary_route in ('MOD_ART191_2_AJENA_LT_1Y',
                                  'MOD_ART191_3_AJENA_GE_1Y',
                                  'MOD_ART191_3_PROPIA_GE_1Y')):
        return 'SHARED_ORIGIN_MODIFICATION_RULE'
    if not routes:
        return 'NO_ROUTE_TAG_REQUIRES_REVIEW'
    return None


def alternative_scope(plan, covered, evidence, dossier, *, call, model, client, report, max_proposals=3):
    """Retry substantive rejections only; never retry transport/integrity failures blindly."""
    max_proposals=max(1,min(3,max_proposals))
    attempts=[]; feedback=[]
    candidates=scope_candidates(plan,dossier)
    candidate_index=0
    for _ in range(max_proposals):
        current={}
        result=_one_scope(plan,covered,evidence,dossier,call=call,model=model,client=client,report=current,feedback=feedback,primary_route=candidates[candidate_index] if candidates else None)
        attempts.append(current)
        report.clear()
        report.update(current)
        report.update(max_proposals=max_proposals,attempts=attempts,scope_candidates=candidates)
        if result is not None: return result
        reason=current.get('reason')
        if reason not in ('COMMERCIAL_SCOPE_CHANGED','FORBIDDEN_ROUTE_IDS','INDEPENDENT_SCOPE_REJECTED','TITLE_NOT_NARROWED','ORIGINAL_BLOCKING_GAPS_NOT_ACCOUNTED_FOR','MISSING_TITLE','REPEATED_PROPOSAL','INVALID_QUESTION_COUNT','SCOPE_ROUTE_MISMATCH','INVALID_QUESTION','DUPLICATE_QUESTION','INCOMPLETE_INDEPENDENT_REVIEW','MISSING_REVIEW_REASON','INVALID_ROUTE_IDS','PASSAGE_WRONG_ROUTE','MATERIAL_SEARCH_FOCUS_LOST'):
            break
        feedback.append({'reason':reason,'title':(current.get('proposal') or {}).get('title') if isinstance(current.get('proposal'),dict) else None,
                         'scope':(current.get('proposal') or {}).get('scope') if isinstance(current.get('proposal'),dict) else None,
                         'forbidden_route_ids':current.get('forbidden_route_ids',[]),
                         'out_of_scope_route_ids':current.get('out_of_scope_route_ids',[]),
                         'review':current.get('independent_scope_review'),
                         'primary_route':current.get('primary_route'),
                         'question_count':current.get('question_count'),
                         'gap_reference_check':current.get('gap_reference_check'),
                         'passage_route_rejection':current.get('passage_route_rejection')})
        if reason in ('INDEPENDENT_SCOPE_REJECTED','REPEATED_PROPOSAL') and candidate_index+1<len(candidates):
            candidate_index+=1
    return None


def _one_scope(plan, covered, evidence, dossier, *, call, model, client, report, feedback, primary_route):
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
    report['primary_route']=primary_route
    if not route_set or primary_route not in route_set:
        report['status']='NO_SELECTABLE_ROUTES'; return None
    records_by_id={p['passage_id']:p for p in selected}
    eligible_aliases=[a for a,pid in alias_map.items() if passage_route_compatibility(records_by_id[pid],primary_route)]
    report['eligible_passage_aliases']=eligible_aliases
    if not eligible_aliases:
        report['status']='NO_ROUTE_COMPATIBLE_PASSAGES'; return None
    proposal_fields={**PROPOSAL_FIELDS,'business_category':{'type':'string','enum':[plan['commercial_classification']['business_category']]},'questions':{**PROPOSAL_FIELDS['questions'],'items':{**PROPOSAL_FIELDS['questions']['items'],'properties':{**CLAIM_FIELDS,'passage_ids':{'type':'array','items':{'type':'string','enum':eligible_aliases}},'route_ids':{'type':'array','items':{'type':'string','enum':[primary_route]}}}}}}
    required_gap_ids=sorted(g['gap_id'] for g in gaps)
    proposal_fields['excluded_gap_ids']={'type':'array','items':{'type':'string','enum':required_gap_ids}}
    # The configured non-fine-tuned GPT-4.1 family supports array bounds.
    # Keep the Python guard for other models and historical responses.
    if model in ('gpt-4.1-mini','gpt-4.1','gpt-4.1-nano') or model.startswith(('gpt-4.1-mini-','gpt-4.1-nano-','gpt-4.1-20')):
        proposal_fields['excluded_gap_ids'].update(minItems=len(required_gap_ids),maxItems=len(required_gap_ids))
        proposal_fields['questions'].update(minItems=2,maxItems=8)
        proposal_fields['questions']['items']['properties']['route_ids'].update(minItems=1,maxItems=1)
    employer_focus=employer_change_focus(plan.get('commercial_classification',{}).get('business_category'),plan.get('topic',''))
    focus_instruction=(' The original search intent specifically concerns renewal when changing employer. Do not remove that topic or treat it as a disclaimer. Narrow to a verified employer-change scenario if appropriate; distinguish the two new-contract alternatives in Article 80.2.b and their conditions when relevant. If the essential rules remain unverified, return no proposal.' if employer_focus else '')
    report['material_search_focus']='EMPLOYER_CHANGE_RENEWAL' if employer_focus else None
    data={'original_plan':plan,'original_coverage':covered,'blocking_gaps':gaps,'official_passages':short_selected,'dossier':dossier,'selectable_route_ids':sorted(route_set),'previous_rejections':feedback,'primary_route':primary_route,'required_question_count':{'min':2,'max':8},'eligible_passage_aliases':eligible_aliases,'required_excluded_gap_ids':required_gap_ids}
    def ask(name, fields, prompt, payload):
        trace={}; report[name+'_transport']=trace
        result=call([{'role':'system','content':prompt},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
                    model=model,client=client,response_format=schema(name,fields),diagnostics=trace)
        report[name]=result
        return result
    try:
        proposal=ask('proposal',proposal_fields,
            'Propose ONE Spanish article exclusively about the primary_route selected by Python, or empty title if none; in that case describe unresolved questions without inventing answers. Same commercial category and genuine search intent. Provide 2 to 8 distinct essential questions. Every question must contain exactly one route ID, the primary_route; never repeat it; do not provide a survey of other routes. Include the primary route’s conditions and limitations, including material dependencies. '
            'If previous_rejections is nonempty, repair a gap-reference formatting error without changing a valid topic; after a substantive rejection propose a genuinely different, narrower scope that addresses the recorded rejection. Prefer a single verified route or a clearly bounded subtopic; do not repeat the original broad modification-and-extension guide under a new title. '
            'Select only eligible_passage_aliases for the primary route. Shared DA20.10/DA21.10 provisions may support common filing and validity rules, not unrelated prórroga claims. Select only the passages necessary for each answer, including controlling exceptions; do not cite ranges of aliases in prose or select the whole catalog. '
            'Do not solve or erase original gaps. Every essential question needs an explicit supported answer with exact short passage aliases (P001 etc.) and applicable route IDs. '
            'Use only selectable route IDs; never include an unresolved or excluded branch even if you list it as a limitation. Do not infer unavailable routes or exceptional eligibility from uncertainty. Include all material conditions, exceptions, deadlines and effects needed for the specific article. '
            'Copy each required_excluded_gap_ids identifier exactly once if the gap is genuinely outside the new scope; if a gap remains a dependency do not present the article as sufficient. Explicitly list each original blocking gap ID outside the new scope, and limitations and individual conditions. Limitations must be reader-facing statements for publication in the draft: identify the single route covered, explicitly state that other routes are not evaluated, and distinguish unverified procedural details from verified requirements. Do not assert that an unresolved route is legally unavailable or that no official guidance exists. No exhaustive title for a partial guide.'+focus_instruction,data)
        if not isinstance(proposal,dict): raise ValueError('INVALID_PROPOSAL')
        for key in ('title','search_intent','scope','utility','seo_rationale','omission_rationale','business_category'):
            if not isinstance(proposal.get(key),str) or not proposal[key].strip(): raise ValueError('MISSING_'+key.upper())
        matching=[f for f in feedback if norm(f.get('title') or '')==norm(proposal['title']) and norm(f.get('scope') or '')==norm(proposal['scope'])]
        refs=proposal.get('excluded_gap_ids')
        gap_refs_valid=(isinstance(refs,list) and all(isinstance(v,str) for v in refs)
                        and sorted(refs)==required_gap_ids)
        # A repaired reference list is not a repeated failed proposal. Permit
        # only this specific repair, and never override a substantive veto.
        if matching:
            repaired=(gap_refs_valid and all(f['reason']=='ORIGINAL_BLOCKING_GAPS_NOT_ACCOUNTED_FOR' for f in matching))
            if not repaired:
                raise ValueError('REPEATED_PROPOSAL')
            report['proposal_reference_repair']='CORRECTED_GAP_IDS_SAME_SCOPE'
        for key in ('limitations','individual_conditions','excluded_gap_ids'):
            if not isinstance(proposal.get(key),list) or any(not isinstance(v,str) or not v.strip() for v in proposal[key]): raise ValueError('INVALID_'+key.upper())
        if not proposal['limitations']: raise ValueError('MISSING_LIMITATIONS')
        report['gap_reference_check']={'expected':required_gap_ids,'received':proposal['excluded_gap_ids'],'valid':gap_refs_valid}
        if not gap_refs_valid: raise ValueError('ORIGINAL_BLOCKING_GAPS_NOT_ACCOUNTED_FOR')
        report['commercial_scope_check']=commercial_scope_check(plan,proposal)
        if not report['commercial_scope_check']['accepted']:
            raise ValueError('COMMERCIAL_SCOPE_CHANGED')
        if employer_focus and not employer_change_focus('cuenta_ajena',proposal['title']):
            raise ValueError('MATERIAL_SEARCH_FOCUS_LOST')
        if proposal['title'].strip().casefold()==plan['topic'].strip().casefold(): raise ValueError('TITLE_NOT_NARROWED')
        questions=proposal.get('questions'); sent=set(report['passages_sent']); records={p['passage_id']:p for p in selected}
        report['question_count']=len(questions) if isinstance(questions,list) else None
        if not isinstance(questions,list) or not 2<=len(questions)<=8: raise ValueError('INVALID_QUESTION_COUNT')
        alt_questions=[]; seen=set(); resolved_questions=[]
        for i,q in enumerate(questions):
            if not isinstance(q,dict) or any(not isinstance(q.get(k),str) or not q[k].strip() for k in ('question','answer')): raise ValueError('INVALID_QUESTION')
            if q['question'].strip().casefold() in seen: raise ValueError('DUPLICATE_QUESTION')
            seen.add(q['question'].strip().casefold())
            refs=q.get('passage_ids'); routes=q.get('route_ids')
            if not isinstance(refs,list) or not refs or any(not isinstance(p,str) for p in refs) or len(set(refs))!=len(refs): raise ValueError('INVALID_PASSAGE_IDS')
            if not isinstance(routes,list) or not routes or any(not isinstance(r,str) for r in routes): raise ValueError('INVALID_ROUTE_IDS')
            forbidden=sorted(set(routes)-route_set)
            if forbidden:
                report['forbidden_route_ids']=forbidden
                report['forbidden_route_question_index']=i
                raise ValueError('FORBIDDEN_ROUTE_IDS')
            if set(routes)!={primary_route}:
                report['out_of_scope_route_ids']=sorted(set(routes)-{primary_route})
                raise ValueError('SCOPE_ROUTE_MISMATCH')
            if len(routes)>1:
                report.setdefault('route_normalizations',[]).append({'question_index':i,'original_route_ids':routes,'normalized_route_ids':[primary_route]})
                routes=[primary_route]
            resolved=[]
            canonical_refs=[alias_map.get(pid,pid) for pid in refs]
            if len(set(canonical_refs))!=len(canonical_refs): raise ValueError('DUPLICATE_PASSAGE_IDS')
            for pid in canonical_refs:
                p=resolve_passage(pid,catalog,evidence,allowed_ids=sent)
                if not p: raise ValueError('INVALID_PASSAGE_ID')
                compatibility=passage_route_compatibility(records[pid],primary_route)
                if compatibility is None:
                    report['passage_route_rejection']={'question_index':i,'passage_id':pid,'primary_route':primary_route,'source_route_ids':records[pid]['route_ids']}
                    raise ValueError('PASSAGE_WRONG_ROUTE')
                if compatibility == 'SHARED_ORIGIN_MODIFICATION_RULE':
                    report.setdefault('shared_passage_uses',[]).append({'question_index':i,'passage_id':pid,'primary_route':primary_route,'reason':compatibility})
                resolved.append(p)
            eid=list(dict.fromkeys(p['evidence_id'] for p in resolved))
            alt_questions.append({'id':f'alt_{i+1}','question':q['question'],'query':q['question']})
            resolved_questions.append({'question_id':f'alt_{i+1}','answer':q['answer'],'evidence_ids':eid,'supporting_passages':resolved,'route_ids':routes})
        # Explicitly disclose deterministic matrix uncertainties as scope limitations.
        # This is a statement of what this guide does not establish, not a legal
        # conclusion or an override of any independent review.
        disclosures=[]
        for row in covered:
            for assessment in row.get('gap_assessments',[]):
                fact=assessment.get('missing_fact')
                if (assessment.get('origin')=='APPLICABILITY_MATRIX' and assessment.get('classification')=='MATERIAL'
                        and isinstance(fact,str) and fact in row.get('blocking_missing_facts',[])):
                    notice='Esta guía no resuelve la siguiente cuestión, que requiere una comprobación jurídica específica: '+fact
                    if notice not in disclosures: disclosures.append(notice)
        if disclosures:
            proposal={**proposal,'limitations':list(dict.fromkeys(proposal['limitations']+disclosures))}
            report['matrix_gap_disclosures']=disclosures
        review_prompt=(
            'Independently audit the proposed NEW scope, not the old guide. The review_target is the article actually proposed; historical_research_context is background, not a checklist of mandatory coverage. all_essential_questions_covered means essential questions of review_target only. Verify each answer against literal official text and applicable routes, all conditions, exceptions, filing rules and timing. '
            'Verify the title and all answers concern only primary_route, not other routes; reject any omitted material dependency of that route. Compare original and proposed substantive scope, not just titles. Reject a broad guide that still depends on the unresolved branch, even if a limitation is stated. '
            'Check each historical gap against the actual primary route, title, answers and reader-facing limitations in review_target. A gap outside that route is not itself grounds for rejection if the limitation makes the boundary clear; do not assume the article claims comprehensive coverage. Read the supplied limitations as part of the proposed article, not as internal notes. Reject if a gap is a genuine dependency, if the limitation is insufficient or misleading, or if any procedural requirement essential to the proposed route is unverified. Explain the specific dependency or missing disclosure in reasons. '
            'Never approve an assertion that an unresolved route does not exist, nor infer exceptional-extension eligibility. '
            'Reject trivial or SEO-irrelevant content, broad titles, incomplete answers, wrong branches and unsupported claims. '
            'Return all supported zero-based question indices, reasons, and explicit booleans. Approve only if every check passes. If rejecting, identify the failed criterion and specific material defect; do not contradict your own findings.'+focus_instruction)
        review_payload={'review_target':{'primary_route':primary_route,'proposal':{**proposal,'questions':[{**q,'route_ids':r['route_ids']} for q,r in zip(questions,resolved_questions)]},'resolved_questions':resolved_questions,'reader_facing_limitations':proposal['limitations']},'historical_research_context':{'original_plan':plan,'original_coverage':covered,'blocking_gaps':gaps},'official_passages':short_selected,'dossier':dossier}
        verdict=ask('independent_scope_review',REVIEW_FIELDS,review_prompt,review_payload)
        # A negative verdict with every individual check passing and complete
        # support is inconsistent, not an approval. Ask once for a fresh audit.
        checks=[k for k in REVIEW_FIELDS if k not in ('approved','supported_question_indices','reasons')]
        def complete(v):
            indices=v.get('supported_question_indices')
            reasons=v.get('reasons')
            return (all(v.get(k) is True for k in checks)
                    and isinstance(indices,list) and all(type(i) is int for i in indices)
                    and sorted(indices)==list(range(len(questions)))
                    and isinstance(reasons,list) and bool(reasons)
                    and all(isinstance(r,str) and r.strip() for r in reasons))
        if isinstance(verdict,dict) and verdict.get('approved') is False and complete(verdict):
            report['review_consistency']='INCONSISTENT_NEGATIVE_VERDICT'
            # Reconsider the same article, not a different proposal. The initial
            # reasons are evidence of a possible objection, not an instruction
            # to reverse the verdict. The new reviewer must explicitly resolve it.
            recheck_fields={**REVIEW_FIELDS,'prior_objections_resolved':{'type':'boolean'},'resolution':STR}
            fresh=ask('independent_scope_recheck',recheck_fields,review_prompt+
                ' Conduct a fresh legal audit of this exact article. The initial verdict is inconsistent. Independently assess every prior objection against the official text. Do not approve merely because other flags were true. If any material objection remains unresolved, reject. Explain the resolution of each prior objection; set prior_objections_resolved true only if every objection is demonstrably nonmaterial or resolved by evidence.',
                {**review_payload,'initial_review':verdict})
            if (not isinstance(fresh,dict) or fresh.get('prior_objections_resolved') is not True
                    or not isinstance(fresh.get('resolution'),str) or not fresh['resolution'].strip()):
                raise ValueError('INDEPENDENT_SCOPE_REJECTED')
            verdict=fresh
        if not isinstance(verdict,dict) or any(verdict.get(k) is not True for k in REVIEW_FIELDS if k not in ('supported_question_indices','reasons')):
            raise ValueError('INDEPENDENT_SCOPE_REJECTED')
        indices=verdict.get('supported_question_indices')
        if not isinstance(indices,list) or any(type(i) is not int for i in indices) or sorted(indices)!=list(range(len(questions))): raise ValueError('INCOMPLETE_INDEPENDENT_REVIEW')
        if not isinstance(verdict.get('reasons'),list) or not verdict['reasons'] or any(not isinstance(r,str) or not r.strip() for r in verdict['reasons']): raise ValueError('MISSING_REVIEW_REASON')
        # Separate alternative plan/coverage; original report remains intact.
        alt_plan={**plan,'topic':proposal['title'],'commercial_classification':{**plan['commercial_classification'],'search_intent':proposal['search_intent']},
                  'research_questions':alt_questions,'adaptive_editorial_scope':{'original_topic':plan['topic'],'scope':proposal['scope'],
                  'excluded_original_gaps':gaps,'limitations':proposal['limitations'],'individual_conditions':proposal['individual_conditions'],
                  'primary_route':primary_route,'approved_answers':resolved_questions,'original_research_coverage_preserved':True}}
        alt_covered=[{**q,'status':'ANSWERED_WITH_EVIDENCE','evidence_ids':a['evidence_ids'],'missing_facts':[],
                      'reason':a['answer'],'draft_readiness':'READY_WITH_DECLARED_LIMITATIONS',
                      'supporting_passages':a['supporting_passages']} for q,a in zip(alt_questions,resolved_questions)]
        report.update({'status':'APPROVED_FOR_DRAFT_ONLY','authorized_plan':alt_plan,'alternative_coverage':alt_covered})
        return alt_plan,alt_covered
    except Exception as exc:
        # Diagnostics retain response/transport; no alternate draft on failure.
        report.update({'status':'REJECTED','reason':str(exc)[:300],'error_type':type(exc).__name__})
        return None
