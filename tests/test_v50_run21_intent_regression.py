"""Run 21: preserve initial-application exclusions alongside general continuity guidance."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import seo_v50 as seo
from temporary_residence_policy_v50 import classify, research_questions

class Run21IntentRegression(unittest.TestCase):
    def test_initial_processing_query_is_excluded(self):
        title = 'Cuanto tarda la regularización masiva en españa: información y trámites oficiales'
        result = classify(title, ['cuanto tarda la regularizacion masiva en espana'], 'regularization_processing')
        self.assertTrue(result['excluded'])
        self.assertEqual(result['exclusion_reason'], 'INITIAL_REGULARIZATION_PROCESSING_NOT_TEMPORARY_RENEWAL')

    def test_general_continuity_topic_remains_allowed(self):
        result = classify('Cómo continuar la residencia tras la regularización extraordinaria de 2026')
        self.assertFalse(result['excluded'])
        questions = research_questions('regularizacion_2026')
        self.assertEqual({x['id'] for x in questions}, {'scope', 'requirements', 'steps'})
        self.assertIn('YA tiene', questions[0]['question'])
        self.assertIn('NO VERIFICADOS', questions[2]['question'])

    def test_gsc_initial_query_cannot_generate_proposal(self):
        row = {'cluster_id':'regularization_processing',
               'proposed_title':'Regularización masiva 2026: tiempo de respuesta',
               'primary_query':'cuanto tarda la regularización masiva en españa',
               'supporting_queries':['cuanto tarda la regularización masiva en españa'],
               'score_breakdown':{'measured_demand':30},'score':30,
               'impressions_28d':5,'impressions_90d':149,'existing_pages':[]}
        with patch.object(seo.baseline, 'rank', return_value=[row]), patch.object(seo, 'metadata_inventory', return_value=[]):
            rows, chosen, proposal = seo.choose({}, {}, ROOT, [], date(2026,11,24))
        self.assertEqual(rows[0]['recommended_action'], 'SKIP')
        self.assertIsNone(chosen)
        self.assertIsNone(proposal)

if __name__ == '__main__':
    unittest.main()
