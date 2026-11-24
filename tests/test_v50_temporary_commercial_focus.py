"""Six independent business-scope regression checks, never pretend these are live legal E2E tests."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from temporary_residence_policy_v50 import classify,SEEDS,research_questions
from legal_content_v50 import plan
from official_sources_v50 import candidates, retrieve_for_topic

class TestTemporaryFocus(unittest.TestCase):
    def test_six_different_legal_intents_have_research_plans(self):
        self.assertEqual(len(SEEDS),6)
        for category,seed in SEEDS.items():
            with self.subTest(category=category):
                proposal={'proposals':[{'cluster_id':'seed_'+category,'proposed_title':seed['proposed_title'],
                    'queries':[seed['primary_query']],'action':'create_article'}]}
                output=plan(proposal)
                self.assertEqual(output['commercial_classification']['business_category'],category)
                self.assertTrue(output['source_registry_complete'])
                self.assertEqual({q['id'] for q in output['research_questions']},{'scope','requirements','steps'})
                self.assertFalse(output['publication_allowed'])
                self.assertGreaterEqual(len(candidates(seed['proposed_title'],output['group'])),1)
    def test_exclude_legacy_and_unrelated(self):
        for topic in ['renovación de residencia permanente','renovar TIE larga duración UE',
                      'cita de huellas para la TIE','duplicado TIE por pérdida',
                      'nacionalidad española por residencia','renovación NIE']:
            with self.subTest(topic=topic):
                self.assertTrue(classify(topic)['excluded'])
                with self.assertRaisesRegex(ValueError,'OUT_OF_SCOPE_TOPIC'):
                    plan({'proposals':[{'cluster_id':'x','proposed_title':topic}]})
    def test_regularization_and_arraigo_do_not_assume_renewal(self):
        for topic in ('renovar residencia de regularización masiva 2026','renovar arraigo social'):
            classification=classify(topic)
            self.assertFalse(classification['excluded'])
            self.assertIsNone(classification['procedure_type'])
            self.assertEqual(classification['legal_procedure'],'PENDING_OFFICIAL_CLASSIFICATION')
    def test_unqualified_generic_topic_is_rejected(self):
        self.assertTrue(classify('renovar mis papeles')['excluded'])
        self.assertTrue(classify('residencia en España')['excluded'])
    def test_specific_official_evidence_remains_unverified(self):
        official_html='<html><title>Información oficial</title><body><p>'+('Documento sujeto a comprobación de normativa. '*35)+'</p></body></html>'
        for category in SEEDS:
            with self.subTest(category=category):
                topic=SEEDS[category]['proposed_title']
                records,errors,attempts=retrieve_for_topic(topic,'renewal',fetch=lambda url: official_html)
                self.assertTrue(records)
                self.assertTrue(all(r['legal_status']=='PROCEDURAL_GUIDANCE_UNVERIFIED' for r in records))
                self.assertTrue(all(r['research_relevance']['semantic_verification_required'] for r in records))
                self.assertFalse(errors)

if __name__=='__main__':unittest.main()
