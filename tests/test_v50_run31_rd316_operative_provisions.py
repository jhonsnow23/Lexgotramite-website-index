"""Run31: the legal operative paragraphs must not be displaced by the BOE preamble."""
import unittest
from scripts import official_sources_v50 as sources


class Run31OperativeDecree(unittest.TestCase):
    def setUp(self):
        self.pre = ("Preámbulo: disposición adicional vigésima y vigesimoprimera. "
                    "Modificación, prórroga, artículo 191. " * 500)
        self.a20 = ("10. La autorización concedida tendrá una vigencia de un año. "
                    "Durante los dos meses previos podrá solicitar una modificación "
                    "conforme al artículo 191. Excepcionalmente, si no se pudiera "
                    "solicitar una modificación, podrá ser prorrogada si se acredita "
                    "búsqueda activa de empleo o informe de esfuerzo de integración. "
                    "Esta prórroga tendrá vigencia de un año. "
                    "No obstante, enfermedad grave o discapacidad podrá habilitar "
                    "una prórroga de cuatro años. ")
        self.a21 = ("10. La autorización de residencia temporal por circunstancias "
                    "excepcionales por razón de arraigo extraordinario tendrá "
                    "una vigencia de un año. Durante los dos meses previos se solicitará "
                    "modificación conforme al artículo 191. Excepcionalmente, si no "
                    "se pudiera modificar, podrá prorrogarse con búsqueda activa de "
                    "empleo e inscripción o informe de esfuerzo de integración. "
                    "Esta prórroga durará un año. No obstante, enfermedad grave "
                    "o discapacidad habilita a cuatro años. ")
        self.body=(self.pre+' Once. Se añade una disposición adicional vigésima. '
                   +self.a20+' Doce. Se añade una disposición adicional vigesimoprimera. '
                   +self.a21+' Trece. La disposición transitoria única.')

    def test_both_operational_sections_are_prioritized(self):
        output=sources.excerpt_for_legal_publication(self.body)
        self.assertIn(self.a20.strip(),output)
        self.assertIn(self.a21.strip(),output)
        self.assertNotIn('Preámbulo:',output)
        self.assertLessEqual(len(output),18000)

    def test_retrieval_uses_operational_text_and_remains_unverified(self):
        html='<html><body><p>'+self.body+'</p></body></html>'
        record=sources.retrieve_one('boe','Real Decreto 316/2026 — texto oficial publicado',
                 'https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8284',
                 fetch=lambda _url:html)
        self.assertIn('Esta prórroga durará un año',record['text'])
        self.assertEqual(record['legal_status'],'OFFICIAL_LEGAL_TEXT_UNVERIFIED')
        self.assertTrue(record['research_relevance']['semantic_verification_required'])

    def test_malformed_operational_sections_use_conservative_fallback(self):
        body='Disposición adicional vigésima. '+'a'*2000
        output=sources.excerpt_for_legal_publication(body)
        self.assertIn('Disposición adicional vigésima',output)
        self.assertIsNone(sources.extract_rd316_continuity_provisions(body))

    def test_long_preamble_cannot_starve_exception_conditions(self):
        body=('artículo 191. disposición adicional vigésima. prórroga. '*3000)+self.body
        result=sources.excerpt_for_legal_publication(body)
        self.assertIn('No obstante, enfermedad grave',result)
        self.assertIn('Esta prórroga durará un año',result)


if __name__ == '__main__':
    unittest.main()
