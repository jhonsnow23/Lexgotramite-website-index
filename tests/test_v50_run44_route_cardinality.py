import copy,json,unittest
from pathlib import Path
from unittest.mock import Mock
from test_v50_run35_branch_applicability import legal
from editorial_scope_v50 import alternative_scope, REVIEW_FIELDS
F=json.loads((Path(__file__).parent/'fixtures/run43_replay.json').read_text())
class Run44Tests(unittest.TestCase):
    def run_scope(self,*responses,limit=1):
        report={}; coverage=copy.deepcopy(F['coverage']); call=Mock(side_effect=responses)
        result=alternative_scope(F['plan'],coverage,F['evidence'],legal.build_dossier(F['plan'],F['evidence']),call=call,model='gpt-4.1-mini',client=None,report=report,max_proposals=limit)
        self.assertEqual(coverage,F['coverage']); self.assertFalse(report['publication_allowed']); return result,report,call
    def verdict(self):
        return {**{k:True for k in REVIEW_FIELDS},'supported_question_indices':list(range(len(F['proposal']['questions']))),'reasons':['Simulated review only']}
    def test_real_duplicate_reaches_review(self):
        result,r,c=self.run_scope(F['proposal'],self.verdict()); self.assertEqual(c.call_count,2,r.get('reason')); self.assertIsNotNone(result,r.get('reason')); self.assertEqual(r['route_normalizations'][0]['question_index'],2)
        props=c.call_args_list[0].kwargs['response_format']['json_schema']['schema']['properties']['questions']['items']['properties']['route_ids']; self.assertEqual((props['minItems'],props['maxItems']),(1,1))
        payload=json.loads(c.call_args_list[1].args[0][1]['content']); self.assertEqual(len(payload['review_target']['proposal']['questions'][2]['route_ids']),1)
        self.assertEqual(len(r['proposal']['questions'][2]['route_ids']),2)
    def test_review_veto(self):
        result,r,c=self.run_scope(F['proposal'],{**self.verdict(),'approved':False}); self.assertIsNone(result); self.assertEqual(r['reason'],'INDEPENDENT_SCOPE_REJECTED')
    def test_mixed_routes_not_normalized(self):
        p=copy.deepcopy(F['proposal']);p['questions'][2]['route_ids'].append('MOD_CUENTA_PROPIA_LT_1Y_UNRESOLVED'); result,r,c=self.run_scope(p); self.assertIsNone(result); self.assertEqual(r['reason'],'FORBIDDEN_ROUTE_IDS'); self.assertEqual(c.call_count,1)
    def test_empty_route_retries(self):
        p=copy.deepcopy(F['proposal']);p['questions'][0]['route_ids']=[]; p['title']+=': requisitos';result,r,c=self.run_scope(p,F['proposal'],self.verdict(),limit=2);self.assertIsNotNone(result,r.get('reason')); self.assertEqual(r['attempts'][0]['reason'],'INVALID_ROUTE_IDS')
