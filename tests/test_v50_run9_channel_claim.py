"""Run 9: assert only established application routes, not research gaps."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from legal_content_v50 import renewal_scope_warnings, SYSTEM_WRITER, SYSTEM_REVIEW
PLAN={'topic':'Renovación de residencia permanente','group':'renewal'}
def article(paragraph):
    return {'introduction':'Renovar la TIE física no renueva la autorización indefinida.',
            'sections':[{'heading':'Dónde presentar','paragraphs':[paragraph]}],
            'faqs':[], 'claims':[]}
class Run9Tests(unittest.TestCase):
    def test_negative_evidence_statement_blocked(self):
        obj=article('No consta evidencia específica de canales telemáticos para la renovación física de la TIE.')
        self.assertTrue(any('lack-of-online-evidence' in x for x in renewal_scope_warnings(obj,PLAN)))
    def test_supported_positive_route_not_blocked(self):
        obj=article('Según la información oficial de la Policía, puede presentar la solicitud en la oficina indicada para este trámite.')
        self.assertEqual([],renewal_scope_warnings(obj,PLAN))
    def test_exclusivity_still_guarded(self):
        obj=article('La solicitud debe presentarse personalmente en cualquier Oficina de Extranjería.')
        self.assertTrue(any('absolute in-person' in x for x in renewal_scope_warnings(obj,PLAN)))
    def test_writer_and_reviewer_have_distinction(self):
        self.assertIn('en términos positivos',SYSTEM_WRITER)
        self.assertIn('La primera puede estar plenamente apoyada',SYSTEM_REVIEW)
if __name__=='__main__': unittest.main()
