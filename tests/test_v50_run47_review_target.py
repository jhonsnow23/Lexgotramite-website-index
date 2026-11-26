import copy,json,unittest
from pathlib import Path
from unittest.mock import Mock
from test_v50_run35_branch_applicability import legal
from editorial_scope_v50 import alternative_scope
F=json.loads((Path(__file__).parent/'fixtures/run46_replay.json').read_text())
class Run47Tests(unittest.TestCase):
    def execute_scope(self,responses,limit=1):
        coverage=copy.deepcopy(F['coverage']); report={}; call=Mock(side_effect=responses)
        result=alternative_scope(F['plan'],coverage,F['evidence'],legal.build_dossier(F['plan'],F['evidence']),call=call,model='gpt-4.1-mini',client=None,report=report,max_proposals=limit)
        self.assertEqual(coverage,F['coverage']); self.assertFalse(report['publication_allowed']); return result,report,call
    def test_real_vetoes_remain_binding(self):
        responses=[v for a in F['attempts'] for v in (a['proposal'],a['verdict'])]
        result,r,c=self.execute_scope(responses,3)
        self.assertIsNone(result); self.assertEqual(c.call_count,6,r.get('reason')); self.assertEqual(len(r['attempts']),3)
        self.assertTrue(all(a['reason']=='INDEPENDENT_SCOPE_REJECTED' for a in r['attempts']))
    def test_review_target_distinct_from_history(self):
        a=F['attempts'][0]; result,r,c=self.execute_scope([a['proposal'],a['verdict']]); self.assertIsNone(result)
        messages=c.call_args_list[1].args[0]; payload=json.loads(messages[1]['content']); target=payload['review_target']; history=payload['historical_research_context']
        self.assertEqual(target['reader_facing_limitations'],a['proposal']['limitations']); self.assertEqual(target['proposal']['title'],a['proposal']['title']); self.assertEqual(history['original_coverage'],F['coverage']); self.assertEqual(len(history['blocking_gaps']),2)
        self.assertIn('essential questions of review_target only',messages[0]['content']); self.assertIn('genuine dependency',messages[0]['content'])
    def test_simulated_approval_preserves_limitations(self):
        a=F['attempts'][0]; verdict={**a['verdict'],'approved':True,'all_essential_questions_covered':True,'no_misleading_omissions':True,'supported_question_indices':list(range(len(a['proposal']['questions']))),'reasons':['Simulated scope approval, not legal verification']}
        result,r,c=self.execute_scope([a['proposal'],verdict]); self.assertIsNotNone(result,r.get('reason')); self.assertEqual(result[0]['adaptive_editorial_scope']['limitations'],a['proposal']['limitations']); self.assertEqual(len(result[0]['adaptive_editorial_scope']['excluded_original_gaps']),2)
