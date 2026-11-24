"""RD316 is a BOE publication, not an indexed consolidated document."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import legal_relevance_v50 as relevance
import official_sources_v50 as official

class TestRD316Routing(unittest.TestCase):
    def test_amending_decree_not_requested_from_consolidated_index(self):
        called=[]
        def fake_index(url):
            called.append(url)
            raise RuntimeError('fixture: cannot fetch')
        _, diagnostics=relevance.discover('arraigo','Cómo continuar la residencia tras la regularización extraordinaria de 2026',index_fetch=fake_index)
        self.assertEqual(len(called),1, 'Amending decree must never be requested through the consolidated index API')
        self.assertIn('BOE-A-2024-24099',called[0])
        self.assertNotIn('BOE-A-2026-8284',called[0])
        self.assertEqual(len(diagnostics),1)

    def test_regularization_includes_official_legal_publication(self):
        sources=official.candidates('Cómo continuar la residencia tras la regularización extraordinaria de 2026','arraigo')
        urls=[x[2] for x in sources]
        self.assertIn('https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8284',urls)

    def test_decree_source_keeps_later_specific_provisions(self):
        body='A'*24000+' Disposición adicional vigésima. Modificación de residencia. '+'Z'*1200+' Disposición adicional vigésima primera. Prórroga extraordinaria. '+'Y'*400
        html='<html><head><title>BOE publicación</title></head><body><p>'+body+'</p></body></html>'
        rec=official.retrieve_one('boe','Real Decreto 316/2026 — texto oficial publicado',
            'https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8284',fetch=lambda _:html)
        self.assertIn('Disposición adicional vigésima',rec['text'])
        self.assertIn('vigésima primera',rec['text'])
        self.assertEqual(rec['research_relevance']['source_type'],'official_legal_publication')
        self.assertEqual(rec['legal_status'],'OFFICIAL_LEGAL_TEXT_UNVERIFIED')
        self.assertLessEqual(len(rec['text']),18100)

    def test_untrusted_hosts_still_rejected(self):
        self.assertFalse(official.allowed('https://www.boe.es.attacker.example/a'))
        self.assertFalse(official.allowed('http://www.boe.es/diario_boe/txt.php'))
        self.assertFalse(official.allowed('https://evil.com/'))

if __name__ == '__main__': unittest.main()
