import copy,json,unittest
from pathlib import Path
from unittest.mock import Mock
from test_v50_run35_branch_applicability import legal
from editorial_scope_v50 import alternative_scope
F=json.loads((Path(__file__).parent/'fixtures/run47_replay.json').read_text())
class Run48Tests(unittest.TestCase):
    def run_case(self,responses,limit=3):
        coverage=copy.deepcopy(F['coverage']); report={}; call=Mock(side_effect=responses)
        result=alternative_scope(F['plan'],coverage,F['evidence'],legal.build_dossier(F['plan'],F['evidence']),call=call,model='gpt-4.1-mini',client=None,report=report,max_proposals=limit)
        self.assertEqual(coverage,F['coverage']); self.assertFalse(report['publication_allowed']); return result,report,call
    def test_actual_veto_then_inconsistent_verdicts_remain_blocked(self):
        responses=[]
        for i,a in enumerate(F['attempts']):
            responses.extend((a['proposal'],a['verdict']))
            if i: responses.append({**a['verdict'],'prior_objections_resolved':False,'resolution':'Unresolved'})
        result,r,c=self.run_case(responses); self.assertIsNone(result);self.assertEqual(c.call_count,8,r.get('reason'));self.assertEqual(len(r['attempts']),3)
        self.assertNotIn('review_consistency',r['attempts'][0]); self.assertEqual(r['attempts'][1]['review_consistency'],'INCONSISTENT_NEGATIVE_VERDICT');self.assertEqual(r['attempts'][2]['independent_scope_review'],F['attempts'][2]['verdict'])
    def test_fresh_review_can_approve_only_with_explicit_resolution(self):
        a,b=F['attempts'][:2]; fresh={**b['verdict'],'approved':True,'prior_objections_resolved':True,'resolution':'Simulated resolution of prior objections','reasons':['Simulated legal audit']}
        result,r,c=self.run_case([a['proposal'],a['verdict'],b['proposal'],b['verdict'],fresh]);self.assertIsNotNone(result,r.get('reason'));self.assertEqual(c.call_count,5)
        self.assertFalse(r['independent_scope_review']['approved']);self.assertTrue(r['independent_scope_recheck']['approved']); payload=json.loads(c.call_args_list[-1].args[0][1]['content']);self.assertEqual(payload['initial_review'],b['verdict']);self.assertNotIn('previous_rejections',payload);self.assertEqual(payload['review_target']['proposal']['title'],b['proposal']['title'])
    def test_no_approval_if_recheck_does_not_resolve_objections(self):
        a,b=F['attempts'][:2]; fresh={**b['verdict'],'approved':True,'prior_objections_resolved':False,'resolution':'Unresolved'}
        result,r,c=self.run_case([a['proposal'],a['verdict'],b['proposal'],b['verdict'],fresh],2);self.assertIsNone(result);self.assertEqual(c.call_count,5);self.assertNotIn('authorized_plan',r)
    def test_transport_failure_stays_blocked(self):
        a,b=F['attempts'][:2];result,r,c=self.run_case([a['proposal'],a['verdict'],b['proposal'],b['verdict'],RuntimeError('simulated API failure')]);self.assertIsNone(result);self.assertEqual(c.call_count,5);self.assertNotIn('authorized_plan',r)
