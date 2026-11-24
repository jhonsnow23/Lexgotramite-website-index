"""Regression for GSC initial-application queries versus commercial continuity intent."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import seo_v50 as seo
from temporary_residence_policy_v50 import classify

class TestRegularizationIntent(unittest.TestCase):
    def test_processing_questions_are_not_continuity(self):
        for title in (
            'Cuanto tarda la regularización masiva en España: información y trámites oficiales',
            'Cómo consultar el estado de solicitud de regularización masiva 2026',
            'Cuándo me aprueban la regularización extraordinaria 2026',
        ):
            with self.subTest(title=title):
                data=classify(title, ['cuanto tarda la regularizacion masiva en espana'], 'regularization_processing')
                self.assertTrue(data['excluded'])
                self.assertEqual(data['exclusion_reason'],'INITIAL_REGULARIZATION_PROCESSING_NOT_TEMPORARY_RENEWAL')
    def test_continuity_stays_eligible(self):
        for title in (
            'Cómo continuar la residencia tras la regularización extraordinaria de 2026',
            'Modificar autorización concedida por regularización masiva 2026',
            'Prórroga de residencia de la regularización extraordinaria 2026',
        ):
            with self.subTest(title=title):
                result=classify(title)
                self.assertFalse(result['excluded'])
                self.assertEqual(result['business_category'],'regularizacion_2026')
    def test_selection_does_not_promote_gsc_processing_intent(self):
        item={
            'cluster_id':'regularization_processing',
            'proposed_title':'Regularización: cómo consultar el estado del expediente',
            'primary_query':'cuanto tarda la regularización masiva en españa',
            'supporting_queries':['cuanto tarda la regularización masiva en españa'],
            'score_breakdown':{'measured_demand':30},'score':30,
            'impressions_28d':5,'impressions_90d':149,
            'existing_pages':[],
        }
        with patch.object(seo.baseline,'rank',return_value=[item]),patch.object(seo,'metadata_inventory',return_value=[]):
            rows,winner,proposal=seo.choose({}, {}, ROOT, [], __import__('datetime').date(2026,11,24))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['recommended_action'],'SKIP')
        self.assertIsNone(winner)
        self.assertIsNone(proposal)

if __name__=='__main__': unittest.main()
