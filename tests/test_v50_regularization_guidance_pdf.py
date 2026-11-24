"""Official post-regularization guidance must reach legal research, not generic FAQs."""
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfWriter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import official_sources_v50 as src

class TestGuidancePDF(unittest.TestCase):
    def test_specific_legal_guidance_discovered(self):
        candidates=src.candidates('Cómo continuar la residencia tras la regularización extraordinaria de 2026','arraigo')
        self.assertGreaterEqual(len([x for x in candidates if src.is_pdf_url(x[2])]),2)
        self.assertFalse(any(u.endswith('/residencia') for _,_,u in candidates))
    def test_gov_pdf_host_allowed(self):
        self.assertTrue(src.allowed('https://inclusion.gob.es/documents/a.pdf/file'))
        self.assertFalse(src.allowed('https://inclusion.gob.es.attacker.test/doc.pdf'))
        self.assertTrue(src.is_pdf_url('https://inclusion.gob.es/documents/a.pdf/opaque?version=1'))
    def test_pdf_extraction(self):
        # Generate in-memory PDF with pypdf; blank pages extract to an empty string.
        f=io.BytesIO();w=PdfWriter();w.add_blank_page(width=200,height=200);w.write(f)
        self.assertEqual(src.extract_pdf_text(f.getvalue()).strip(),'')
    def test_pdf_rejects_bad_payload(self):
        with self.assertRaisesRegex(ValueError,'Expected PDF'):
            src.retrieve_one('migraciones','PDF','https://inclusion.gob.es/a.pdf/id',fetch=lambda u:'<html>bad</html>')
    def test_excerpt_prioritizes_modification(self):
        long='Información de solicitud inicial. '*1000
        legal='MODIFICACIÓN O PRÓRROGA DE AUTORIZACIONES. No es renovable. Se podrá modificar de acuerdo con el artículo 191.'
        excerpt=src.excerpt_for_procedure_guidance(long+legal+' Texto adicional.'*50)
        self.assertIn('No es renovable',excerpt)
        self.assertIn('artículo 191',excerpt)
        self.assertNotIn(long[:1000],excerpt)
    def test_boe_html_route_unchanged(self):
        html='<html><body><p>'+'Disposición adicional vigésima. '+'A'*500+'</p></body></html>'
        rec=src.retrieve_one('boe','RD316','https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8284',fetch=lambda _:html)
        self.assertEqual(rec['legal_status'],'OFFICIAL_LEGAL_TEXT_UNVERIFIED')
        self.assertIn('vigésima',rec['text'])

if __name__=='__main__':unittest.main()
