import copy,json,unittest
from pathlib import Path
from unittest.mock import Mock
from test_v50_run35_branch_applicability import legal
from editorial_scope_v50 import alternative_scope,scope_candidates,REVIEW_FIELDS
from evidence_passages_v50 import build_catalog,select_context,short_passage_context
F=json.loads((Path(__file__).parent/'fixtures/run42_replay.json').read_text())
class Run43Tests(unittest.TestCase):
    def setUp(self):
        self.plan=F['plan']; self.covered=F['coverage']; self.e=F['evidence']; self.d=legal.build_dossier(self.plan,self.e); self.report={}
    def narrow(self,route='MOD_ART191_2_AJENA_LT_1Y',art='74'):
        from test_v50_run39_passages_scope import Run39Tests
        h=Run39Tests();h.setUp(); p=h.proposal([f'{q["id"]}:{i}' for q in self.covered for i,_ in enumerate(q.get('blocking_missing_facts') or [])]);
        cat=build_catalog(self.e); selected,_=select_context(cat,self.e,self.d); aliases,_=short_passage_context(selected); rev={v:k for k,v in aliases.items()}
        for q,a in zip(p['questions'],('191',art)):
            q['route_ids']=[route]; q['passage_ids']=[rev[next(x['passage_id'] for x in selected if x['article_reference']==a and not x['parent_passage_id'])]]
        if art=='80': p['title']=p['title'].replace('antes del año','a partir de un año'); p['scope']='Employed work after one year'
        return p,h.verdict()
    def run_scope(self,*responses):
        call=Mock(side_effect=responses); original=copy.deepcopy(self.covered)
        result=alternative_scope(self.plan,self.covered,self.e,self.d,call=call,model='test',client=None,report=self.report)
        self.assertEqual(self.covered,original);self.assertFalse(self.report['publication_allowed']);return result,call
    def test_actual_run42_replays_both_failures_then_narrow_scope(self):
        p,v=self.narrow(); result,call=self.run_scope(F['attempts'][0]['proposal'],F['attempts'][1]['proposal'],p,v)
        self.assertIsNotNone(result,self.report.get('reason'));self.assertEqual(call.call_count,4)
        self.assertEqual([a.get('reason') for a in self.report['attempts']],['SCOPE_ROUTE_MISMATCH','INVALID_QUESTION_COUNT',None])
        data=json.loads(call.call_args_list[2].args[0][1]['content']);self.assertEqual(data['previous_rejections'][1]['question_count'],1);self.assertEqual(data['required_question_count'],{'min':2,'max':8})
        self.assertEqual(result[0]['adaptive_editorial_scope']['primary_route'],'MOD_ART191_2_AJENA_LT_1Y')
    def test_independent_veto_rotates_branch_and_retains_reasons(self):
        p,v=self.narrow(); p2,v2=self.narrow('MOD_ART191_3_AJENA_GE_1Y','80'); veto={**v,'approved':False,'no_misleading_omissions':False,'reasons':['Material condition missing']}
        result,call=self.run_scope(p,veto,p2,v2); self.assertIsNotNone(result,self.report.get('reason'))
        payload=json.loads(call.call_args_list[2].args[0][1]['content']);self.assertEqual(payload['previous_rejections'][0]['review']['reasons'],veto['reasons']);self.assertEqual(payload['primary_route'],'MOD_ART191_3_AJENA_GE_1Y')
    def test_closed_schema_and_candidate_excludes_umbrella(self):
        candidates=scope_candidates(self.plan,self.d); self.assertNotIn('MODIFICACION_ART_191',candidates); self.assertNotIn('MOD_CUENTA_PROPIA_LT_1Y_UNRESOLVED',candidates)
        p,v=self.narrow();result,call=self.run_scope(p,v);self.assertIsNotNone(result)
        props=call.call_args_list[0].kwargs['response_format']['json_schema']['schema']['properties'];self.assertEqual(props['questions']['items']['properties']['route_ids']['items']['enum'],[candidates[0]])
    def test_single_question_stays_invalid_and_exhausts(self):
        p,v=self.narrow();p['questions']=p['questions'][:1]
        # Distinct title/scope each time to exercise the count guard.
        p2={**p,'title':p['title']+' (condiciones)','scope':p['scope']+' 2'};p3={**p,'title':p['title']+' (requisitos)','scope':p['scope']+' 3'}
        result,call=self.run_scope(p,p2,p3);self.assertIsNone(result);self.assertEqual(call.call_count,3);self.assertEqual([a['reason'] for a in self.report['attempts']],['INVALID_QUESTION_COUNT']*3)
    def test_no_independent_approval_never_generates_scope(self):
        p,v=self.narrow();p2,v2=self.narrow('MOD_ART191_3_AJENA_GE_1Y','80');p3,v3=self.narrow('MOD_ART191_3_PROPIA_GE_1Y','86');p3['title']='Modificación por cuenta propia tras la regularización extraordinaria de 2026 a partir de un año';p3['scope']='Self employed after one year'
        result,call=self.run_scope(p,{**v,'approved':False,'no_misleading_omissions':False},p2,{**v2,'approved':False,'no_misleading_omissions':False},p3,{**v3,'approved':False,'no_misleading_omissions':False});self.assertIsNone(result);self.assertEqual(call.call_count,6);self.assertNotIn('authorized_plan',self.report)
    def test_configured_model_schema_question_bounds(self):
        p,v=self.narrow();call=Mock(side_effect=[p,v]);report={}
        self.assertIsNotNone(alternative_scope(self.plan,self.covered,self.e,self.d,call=call,model='gpt-4.1-mini',client=None,report=report))
        q=call.call_args_list[0].kwargs['response_format']['json_schema']['schema']['properties']['questions']
        self.assertEqual((q['minItems'],q['maxItems']),(2,8))
        self.assertFalse(report['publication_allowed'])
