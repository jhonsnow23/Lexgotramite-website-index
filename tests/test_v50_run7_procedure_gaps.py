"""Run-7 regressions: distinguish material legal gaps from optional coverage."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from legal_content_v50 import SYSTEM_WRITER, SYSTEM_REVIEW, renewal_scope_warnings, verify_integrity, semantic_review

class Run7Tests(unittest.TestCase):
    def setUp(self):
        self.plan = {'topic': 'Renovación de residencia permanente', 'group':'renewal',
                     'source_registry_complete': True, 'existing_page_action':'create_article'}
        self.article = {'title':'T'*42,'meta_description':'M'*45,'introduction':'I'*70,
             'sections':[{'heading':'Trámite y documentación','paragraphs':['Texto de prueba '*8]} for _ in range(3)],
             'faqs':[], 'claims':[{'claim':'La TIE física se renueva tras su caducidad', 'evidence_ids':['EV1']}],
             'unresolved_questions':[]}
        self.evidence = [{'evidence_id':'EV1', 'version_status':'CURRENT', 'text':'Evidence placeholder'}]
    def test_unresolved_material_question_still_blocks(self):
        self.article['unresolved_questions']=['Canal indispensable sin verificar']
        self.assertIn('Unresolved legal questions', verify_integrity(self.article,self.evidence,self.plan))
    def test_false_periodic_authorization_renewal_in_faq_blocks(self):
        self.article['faqs']=[{'question':'¿Renovar TIE equivale a renovar residencia?',
           'answer':'La autorización de residencia se renueva mediante un procedimiento distinto.'}]
        self.assertTrue(any('FAQ 1' in x for x in renewal_scope_warnings(self.article,self.plan)))
    def test_writer_does_not_infer_absence_from_missing_evidence(self):
        self.assertIn('NO prueba que no exista', SYSTEM_WRITER)
        self.assertIn('autorización indefinida', SYSTEM_WRITER)
    def test_reviewer_distinguishes_material_gaps_from_editorial_notes(self):
        self.assertIn('editorial_notes',SYSTEM_REVIEW)
        self.assertIn('gaps SOLO',SYSTEM_REVIEW)
    def test_reviewer_still_blocks_material_gaps(self):
        def mock(payload):
            return {'choices':[{'message':{'content': '{"assessment":[{"claim_index":0,"status":"SUPPORTED","reason":"test"}],"gaps":["Claim not supported"]}'}}]}
        _,issues=semantic_review(self.article,self.evidence,client=mock)
        self.assertIn('Reviewer identified coverage gaps',issues)

if __name__=='__main__': unittest.main()
