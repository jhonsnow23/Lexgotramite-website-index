"""Regression tests for the Ministry's letter-spaced PDF extraction."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import official_sources_v50 as sources

class TestRun16PDFNormalization(unittest.TestCase):
    def test_spaced_document_is_normalized(self):
        sample=(('S o l i c i t u d   i n i c i a l\n')*25+
          '3 9 . ¿ Q u é  t e n g o  q u e  h a c e r ?\n'+
          'E n  l o s  d o s  m e s e s  p r e v i o s  a  l a  c a d u c i d a d\n'+
          's e  d e b e  m o d i f i c a r  s e g ú n  e l  a r t í c u l o  1 9 1 .')
        normalized=sources.normalize_letter_spaced_pdf_text(sample)
        self.assertIn('Solicitud inicial',normalized)
        self.assertIn('En los dos meses previos a la caducidad',normalized)
        self.assertIn('artículo 191',normalized)
        self.assertIn('modificar',normalized)
        excerpt=sources.excerpt_for_procedure_guidance(normalized)
        self.assertIn('artículo 191',excerpt)
    def test_normal_prose_remains_unchanged(self):
        original='El artículo 191 regula determinadas modificaciones. La autorización tiene vigencia legal.'
        self.assertEqual(sources.normalize_letter_spaced_pdf_text(original),original)
    def test_no_change_to_official_gate(self):
        self.assertFalse(sources.allowed('https://inclusion.gob.es.evil.example/file.pdf'))
        self.assertTrue(sources.allowed('https://inclusion.gob.es/documents/file.pdf'))

if __name__=='__main__':unittest.main()
