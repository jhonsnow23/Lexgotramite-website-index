import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import official_sources_v50 as official
import legal_content_v50 as legal


class TestRegularizationContinuity(unittest.TestCase):
    def test_pdf_limit_increased_but_bounded(self):
        import inspect
        source = inspect.getsource(official.retrieve_one)
        self.assertIn('15_000_000 if pdf', source)
        self.assertIn('read(max_bytes+1)', source)
        self.assertTrue(official.allowed('https://inclusion.gob.es/file.pdf'))
        self.assertFalse(official.allowed('https://evil.example/file.pdf'))

    def test_letter_spaced_guidance_finds_later_continuity(self):
        body = ('Solicitud inicial. ' * 1200 +
                'M O D I F I C A C I Ó N   O   P R Ó R R O G A  D E  A U T O R I Z A C I O N E S. ' +
                'A R T Í C U L O  1 9 1 y explicación.' + ' Aclaración legal. '*200)
        excerpt = official.excerpt_for_procedure_guidance(body)
        self.assertIn('P R Ó R R O G A', excerpt)
        self.assertTrue(len(excerpt) < 18001)

    def test_writer_and_reviewer_distinguish_initial_and_later_procedure(self):
        self.assertIn('ACCESO INICIAL', legal.SYSTEM_WRITER)
        self.assertIn('posterior', legal.SYSTEM_WRITER)
        self.assertIn('CONTINUAR', legal.SYSTEM_REVIEW)

    def test_initial_arrraigo_as_continuity_remains_blocked(self):
        article = {
            'claims':[{'claim':'Continuidad de la autorización extraordinaria según normativa', 'evidence_ids':['EV_REAL']}],
            'sections':[{'heading':'Trámite', 'paragraphs':['Para continuar su residencia se puede solicitar una autorización de arraigo extraordinario.' + ' Detalle.'*8]}] * 3,
            'title':'Cómo continuar la residencia tras la regularización extraordinaria de 2026',
            'meta_description':'Esta descripción explica el procedimiento posterior a la autorización.',
            'introduction':'Información sobre continuidad posterior a autorización ya concedida.',
            'faqs':[], 'unresolved_questions':[],
        }
        plan={'source_registry_complete': True,'commercial_classification':{'business_category':'regularizacion_2026','excluded':False},'existing_page_action':'create_article'}
        errors=legal.verify_integrity(article,[{'evidence_id':'EV_REAL'}],plan)
        self.assertTrue(any('initial extraordinary' in err for err in errors), errors)

    def test_fabricated_id_remains_blocking(self):
        evidence = [{'evidence_id':'EV_REAL'}]
        article = {'claims':[{'claim':'Una afirmación jurídica considerable y específica',
                              'evidence_ids':['EV_REAL_PLUS_HASH']}],
                   'sections':[{'heading':'uno','paragraphs':['a'*70]}]*3,
                   'title':'Título de prueba de continuación extraordinaria de 2026',
                   'meta_description':'Descripción de prueba con longitud suficiente',
                   'introduction':'Introducción de prueba con longitud suficiente',
                   'faqs':[], 'unresolved_questions':[]}
        plan = {'source_registry_complete':True,'commercial_classification':{},'existing_page_action':'create_article'}
        errors = legal.verify_integrity(article,evidence,plan)
        self.assertTrue(any('unknown evidence ID' in e for e in errors))

if __name__=='__main__':unittest.main()
