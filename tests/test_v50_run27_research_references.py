import json
import unittest
from unittest.mock import patch

from scripts import legal_content_v50 as legal


class ResearchReferenceTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'topic':'Continuidad de regularización extraordinaria',
                     'research_questions':[{'id':'scope','question':'¿Qué vía está acreditada?'}]}
        self.evidence = [
            {'evidence_id':'EV_111111111111111111111111','text':'Fuente 1'},
            {'evidence_id':'EV_222222222222222222222222','text':'Fuente 2'},
        ]

    def test_short_alias_maps_to_original_identifier(self):
        def model(messages, **kwargs):
            supplied=json.loads(messages[1]['content'])['evidence']
            self.assertEqual([x['evidence_id'] for x in supplied],['R001','R002'])
            return {'questions':[{'id':'scope','status':'ANSWERED_WITH_EVIDENCE',
                                  'evidence_ids':['R002'],'reason':'Ejemplo de respuesta'}]}
        with patch.object(legal,'call_model',side_effect=model):
            covered,ready=legal.research_readiness(self.plan,self.evidence)
        self.assertTrue(ready)
        self.assertEqual(covered[0]['evidence_ids'],[self.evidence[1]['evidence_id']])

    def test_fabricated_alias_does_not_count_as_evidence(self):
        with patch.object(legal,'call_model',return_value={'questions':[
            {'id':'scope','status':'ANSWERED_WITH_EVIDENCE',
             'evidence_ids':['R002_FAKE','R999'],'reason':'No existe'}]}):
            covered,ready=legal.research_readiness(self.plan,self.evidence)
        self.assertFalse(ready)
        self.assertEqual(covered[0]['status'],'NOT_ANSWERED')
        self.assertEqual(covered[0]['evidence_ids'],[])

    def test_citations_do_not_override_partial_legal_judgment(self):
        with patch.object(legal,'call_model',return_value={'questions':[
            {'id':'scope','status':'PARTIALLY_ANSWERED',
             'evidence_ids':['R001'],'missing_facts':['Norma de excepción'],
             'reason':'Información incompleta'}]}):
            covered,ready=legal.research_readiness(self.plan,self.evidence)
        self.assertFalse(ready)
        self.assertEqual(covered[0]['status'],'PARTIALLY_ANSWERED')
        self.assertEqual(covered[0]['evidence_ids'],[self.evidence[0]['evidence_id']])
        self.assertEqual(covered[0]['missing_facts'],['Norma de excepción'])


if __name__=='__main__': unittest.main()
