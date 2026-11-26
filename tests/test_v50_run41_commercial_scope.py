import json
import unittest
from pathlib import Path
from unittest.mock import Mock
from test_v50_run35_branch_applicability import legal
from temporary_residence_policy_v50 import classify, SEEDS
from editorial_scope_v50 import alternative_scope, REVIEW_FIELDS

F=json.loads((Path(__file__).parent/'fixtures/run40_replay.json').read_text())

class Run41Tests(unittest.TestCase):
    def test_actual_title(self):
        self.assertEqual(classify(F['proposal']['title'])['business_category'],'regularizacion_2026')
    def test_narrow_synonym(self):
        for title in ('Modificación por cuenta ajena tras la autorización extraordinaria de 2026', 'Prórroga para titulares de autorización extraordinaria de 2026'):
            self.assertEqual(classify(title)['business_category'],'regularizacion_2026')
    def test_initial_card_and_other_exclusions(self):
        for title in ('Cómo solicitar autorización extraordinaria de 2026','Cómo solicitar autorización extraordinaria de 2026 para continuar residencia','Renovación TIE tras la autorización extraordinaria de 2026','Continuidad de residencia permanente tras la autorización extraordinaria de 2026','Nacionalidad tras la autorización extraordinaria de 2026: continuidad','Continuidad de residencia no lucrativa tras la autorización extraordinaria de 2026','Autorización extraordinaria de 2026'):
            with self.subTest(title=title): self.assertTrue(classify(title)['excluded'])
    def test_six_seeds(self):
        for key,seed in SEEDS.items(): self.assertEqual(classify(seed['proposed_title'])['business_category'],key)
    def test_real_proposal_does_not_bypass_review(self):
        e=F['evidence']; plan=F['plan']; report={}
        verdict={**{k:False for k in REVIEW_FIELDS if k not in ('supported_question_indices','reasons')},'supported_question_indices':[],'reasons':['Simulated veto: broad scope remains unverified']}
        call=Mock(side_effect=[F['proposal'],verdict])
        result=alternative_scope(plan,F['coverage'],e,legal.build_dossier(plan,e),call=call,model='test',client=None,report=report,max_proposals=1)
        self.assertIsNone(result); self.assertFalse(report['publication_allowed']); self.assertEqual(report['commercial_scope_check']['title_classification']['business_category'],'regularizacion_2026')
        self.assertNotEqual(report['reason'],'COMMERCIAL_SCOPE_CHANGED')
        self.assertEqual(call.call_count,1)
        self.assertEqual(report['reason'],'SCOPE_ROUTE_MISMATCH')
        self.assertEqual(report['original_coverage'],F['coverage'])
