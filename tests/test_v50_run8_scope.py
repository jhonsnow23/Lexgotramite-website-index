"""Run 8: deterministic safeguards against TIE versus authorization claims."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from legal_content_v50 import renewal_scope_warnings, SYSTEM_WRITER

PLAN={'topic':'Renovación de residencia permanente','group':'renewal'}
def sample():
    return {'introduction':'La autorización es indefinida y renovar la TIE no equivale a renovar la autorización.',
            'sections':[{'heading':'Diferencias','paragraphs':['La renovación física de la TIE actualiza el documento.']}],
            'faqs':[], 'claims':[]}

class Run8Tests(unittest.TestCase):
    def test_bad_authorization_renewal_in_section(self):
        a=sample();a['sections'][0]['paragraphs'].append('La autorización de residencia de larga duración nacional se concede y puede renovarse mediante procedimientos específicos.')
        self.assertTrue(any('Section 1: potential renewal' in x for x in renewal_scope_warnings(a,PLAN)))
    def test_negative_explanation_is_not_flagged(self):
        self.assertEqual(renewal_scope_warnings(sample(),PLAN),[])
    def test_absolute_in_person_channel_flagged(self):
        a=sample();a['sections'][0]['paragraphs'].append('La solicitud debe presentarse personalmente en cualquier Oficina de Extranjería.')
        self.assertTrue(any('absolute in-person' in x for x in renewal_scope_warnings(a,PLAN)))
    def test_writing_rules_preserve_material_uncertainties(self):
        self.assertIn('instrucción imprescindible',SYSTEM_WRITER)
        self.assertIn('EN NINGUNA PARTE',SYSTEM_WRITER)

if __name__=='__main__':unittest.main()
