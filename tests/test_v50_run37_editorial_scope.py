import json
import unittest
from unittest.mock import patch
from test_v50_run35_branch_applicability import evidence_fixture, legal
from legal_applicability_v50 import build_dossier


class Run37Tests(unittest.TestCase):
    def setUp(self):
        self.rows, self.plan = evidence_fixture()
        self.plan['research_questions'] = [{'id':'requirements','question':'General conditional routes'}]
        self.dossier = build_dossier(self.plan,self.rows)
        self.fact = 'Whether own-account modification before one year is legally possible'
        self.judgment = {'questions':[{'id':'requirements','status':'PARTIALLY_ANSWERED',
                          'evidence_ids':['R001'],'missing_facts':[self.fact]}]}
        self.assessment = {'index':0,'classification':'EDITORIAL_EXCLUSION',
                           'reason':'General overview can retain evidenced routes without deciding this one',
                           'retained_answer':'Explain evidenced conditional routes only',
                           'limitation':'Do not conclude impossibility or eligibility for exceptional extension',
                           'evidence_ids':['R001'], 'supporting_passages':[{'evidence_id':'R001','quote':self.rows[0]['text'][:120]}]}

    def run_case(self, assessments):
        with patch.object(legal,'call_model',side_effect=[self.judgment,{'assessments':assessments}]) as mock:
            covered,ready=legal.research_readiness(self.plan,self.rows,dossier=self.dossier)
        self.assertEqual(mock.call_count,2)
        payload=json.loads(mock.call_args.args[0][1]['content'])
        self.assertEqual(payload['original_questions'],self.plan['research_questions'])
        return covered[0],ready

    def test_exclusion_preserves_partial_status_and_gap(self):
        q,ready=self.run_case([self.assessment])
        self.assertTrue(ready)
        self.assertEqual(q['status'],'PARTIALLY_ANSWERED')
        self.assertEqual(q['missing_facts'],[self.fact])
        self.assertEqual(q['editorial_exclusions'],[self.fact])
        self.assertEqual(q['gap_assessments'][0]['evidence_ids'],[self.rows[0]['evidence_id']])

    def test_material_gap_blocks(self):
        q,ready=self.run_case([{**self.assessment,'classification':'MATERIAL'}])
        self.assertFalse(ready)
        self.assertEqual(q['blocking_missing_facts'],[self.fact])

    def test_essential_filing_step_blocks_even_with_optional_words(self):
        self.judgment['questions'][0]['missing_facts']=['Exclusive filing channel and mandatory filing deadline not established']
        self.assertFalse(self.run_case([{**self.assessment,'classification':'MATERIAL'}])[1])

    def test_invalid_assessments_fail_closed(self):
        for bad in ([],[{**self.assessment,'evidence_ids':['R999']}],
                    [{**self.assessment,'limitation':''}], [{**self.assessment,'index':1}],
                    [self.assessment,self.assessment]):
            with self.subTest(bad=bad):
                self.assertFalse(self.run_case(bad)[1])

    def test_partial_without_missing_facts_blocks(self):
        self.judgment['questions'][0]['missing_facts']=[]
        with patch.object(legal,'call_model',return_value=self.judgment) as mock:
            q,ready=legal.research_readiness(self.plan,self.rows,dossier=self.dossier)
        self.assertFalse(ready)
        self.assertEqual(mock.call_count,1)

    def test_reviewer_receives_original_scope_and_can_veto(self):
        q,ready=self.run_case([self.assessment]);self.assertTrue(ready)
        with patch.object(legal,'call_model',return_value={'assessment':[], 'gaps':['Omitted material condition']}) as mock:
            _,issues=legal.semantic_review({'claims':[]},self.rows,dossier=self.dossier,
                                           research_coverage=[q],research_plan=self.plan)
        self.assertTrue(issues)
        payload=json.loads(mock.call_args.args[0][1]['content'])
        self.assertEqual(payload['research_coverage'],[q])
        self.assertEqual(payload['research_plan'],self.plan)

    def test_reviewer_must_explicitly_approve_exclusions(self):
        q,ready=self.run_case([self.assessment]);self.assertTrue(ready)
        for verdict, expected in [(None,True),('BLOCKED',True),('SUPPORTED',False)]:
            with patch.object(legal,'call_model',return_value={'assessment':[], 'gaps':[],
                              'scope_limitations_status':verdict}):
                _,issues=legal.semantic_review({'claims':[]},self.rows,dossier=self.dossier,
                                               research_coverage=[q],research_plan=self.plan)
            self.assertEqual(bool(issues),expected)

    def test_temporal_rules_remain_distinct(self):
        variables=' '.join(self.dossier['procedure_context']['decision_variables'])
        self.assertIn('como titular de una autorización',variables)
        self.assertIn('en España en situación de residencia',variables)

if __name__=='__main__': unittest.main()
