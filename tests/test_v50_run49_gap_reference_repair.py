import copy,json,unittest
from pathlib import Path
from unittest.mock import Mock
from test_v50_run35_branch_applicability import legal
from editorial_scope_v50 import alternative_scope
F=json.loads((Path(__file__).parent/'fixtures/run48_replay.json').read_text())
class Run49Tests(unittest.TestCase):
    def run_case(self,responses,limit=3):
        coverage=copy.deepcopy(F['coverage']); report={}; call=Mock(side_effect=responses)
        result=alternative_scope(F['plan'],coverage,F['evidence'],legal.build_dossier(F['plan'],F['evidence']),call=call,model='gpt-4.1-mini',client=None,report=report,max_proposals=limit)
        self.assertEqual(coverage,F['coverage']); self.assertFalse(report['publication_allowed']); return result,report,call
    def test_real_repair_reaches_review_and_veto_stays_binding(self):
        a,b,c=F['attempts']; veto={**c['verdict'],'supported_question_indices':list(range(len(b['proposal']['questions'])))}
        result,r,m=self.run_case([a['proposal'],b['proposal'],veto,c['proposal'],c['verdict']])
        self.assertIsNone(result); self.assertEqual(m.call_count,5)
        self.assertEqual([x['reason'] for x in r['attempts']],['ORIGINAL_BLOCKING_GAPS_NOT_ACCOUNTED_FOR','INDEPENDENT_SCOPE_REJECTED','INDEPENDENT_SCOPE_REJECTED'])
        self.assertEqual(r['attempts'][1]['proposal_reference_repair'],'CORRECTED_GAP_IDS_SAME_SCOPE')
        self.assertEqual(r['attempts'][2]['independent_scope_review'],c['verdict'])
    def test_schema_and_feedback_reference_exact_ids(self):
        a,b=F['attempts'][:2]; result,r,m=self.run_case([a['proposal'],b['proposal'],RuntimeError('simulated API failure')],2)
        self.assertIsNone(result); props=m.call_args_list[0].kwargs['response_format']['json_schema']['schema']['properties']['excluded_gap_ids']
        self.assertEqual(props,{'type':'array','items':{'type':'string','enum':['requirements:0']},'minItems':1,'maxItems':1})
        data=json.loads(m.call_args_list[1].args[0][1]['content']); self.assertEqual(data['previous_rejections'][0]['gap_reference_check']['received'],[])
    def test_unknown_or_duplicate_gap_ids_never_approve(self):
        p=F['attempts'][1]['proposal']
        for refs in [['fake'],['requirements:0','requirements:0']]:
            result,r,m=self.run_case([{**p,'excluded_gap_ids':refs}],1)
            self.assertIsNone(result); self.assertEqual(r['reason'],'ORIGINAL_BLOCKING_GAPS_NOT_ACCOUNTED_FOR');self.assertEqual(m.call_count,1)
    def test_unchanged_invalid_proposal_is_still_repeated(self):
        p=F['attempts'][0]['proposal']; result,r,m=self.run_case([p,p],2)
        self.assertIsNone(result);self.assertEqual(r['reason'],'REPEATED_PROPOSAL'); self.assertEqual(m.call_count,2)
