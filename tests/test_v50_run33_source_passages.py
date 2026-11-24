"""Run 33: prevent clipped legal quotes and overbroad route tagging."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from legal_claim_graph_v50 import _sentences, _passage_routes

class Run33Tests(unittest.TestCase):
    def test_no_cutting_long_sentences_midway(self):
        source='Artículo 191. ' + 'Los requisitos de la modificación se valoran según la modalidad concreta, ' * 9 + 'sin universalizar condiciones.'
        result=_sentences(source)
        self.assertEqual(result,[source.split('Artículo 191. ',1)[1]])
        self.assertTrue(result[0].startswith('Los requisitos'))

    def test_exceptional_prorroga_is_not_modification(self):
        routes=['MODIFICACION_ART_191','PRORROGA_EXCEPCIONAL']
        self.assertEqual(_passage_routes('Excepcionalmente, la autorización podrá ser prorrogada.', routes), ['PRORROGA_EXCEPCIONAL'])

    def test_procedural_extension_is_not_exceptional_prorroga(self):
        routes=['MODIFICACION_ART_191','PRORROGA_EXCEPCIONAL']
        self.assertEqual(_passage_routes('La presentación de la solicitud prorrogará la validez de la autorización anterior.', routes), ['MODIFICACION_ART_191'])

    def test_modification_is_not_exceptional_prorroga(self):
        routes=['MODIFICACION_ART_191','PRORROGA_EXCEPCIONAL']
        self.assertEqual(_passage_routes('Los titulares podrán solicitar una modificación conforme al artículo 191.',routes),['MODIFICACION_ART_191'])

    def test_ambiguous_passage_does_not_claim_both_routes(self):
        routes=['MODIFICACION_ART_191','PRORROGA_EXCEPCIONAL']
        self.assertEqual(_passage_routes('Los titulares de la autorización.',routes),[])

if __name__=='__main__': unittest.main()
