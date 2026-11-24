"""Run 30: verify actual official-index IDs, never guessed BOE block IDs."""
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import legal_relevance_v50 as relevance


class Article191DiscoveryTests(unittest.TestCase):
    @staticmethod
    def fake_index():
        root = ET.Element('indice')
        for num in range(1, 266):
            ET.SubElement(root, 'bloque', id='actual-index-block-' + str(num),
                          titulo=f'Artículo {num}')
        return root

    def test_post_grant_continuity_fetches_observed_article191_index_entry(self):
        calls = []
        def index_fetch(url):
            calls.append(url)
            return self.fake_index(), 'official-index-test-fixture'
        candidates, reports = relevance.discover(
            'arraigo', 'Cómo continuar la residencia tras la regularización extraordinaria de 2026',
            index_fetch=index_fetch, full_text_probe_limit=48)
        matches = [c for c in candidates if c['article'] == '191']
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['block_id'], 'actual-index-block-191')
        self.assertEqual(matches[0]['discovery_method'], 'STRATIFIED_FULL_TEXT_PROBE')
        self.assertEqual(len(candidates), 48)
        self.assertEqual(len(calls), 1)
        self.assertIn('BOE-A-2024-24099', calls[0])
        self.assertEqual(reports[0]['uninspected_index_articles'], 217)

    def test_no_guessed_article_when_index_does_not_contain_191(self):
        root = self.fake_index()
        root.remove(next(n for n in root if n.attrib['titulo'] == 'Artículo 191'))
        candidates, _ = relevance.discover(
            'arraigo', 'Cómo continuar la residencia tras la regularización extraordinaria de 2026',
            index_fetch=lambda _: (root, 'fixture'), full_text_probe_limit=48)
        self.assertFalse(any(c['article'] == '191' for c in candidates))

    def test_initial_regularization_does_not_force_modification_191(self):
        self.assertEqual(relevance._topic_priority_articles(
            'arraigo', 'Solicitud inicial de regularización extraordinaria 2026'), ())

    def test_existing_long_term_priority_unchanged(self):
        self.assertEqual(relevance._topic_priority_articles(
            'renewal', 'Renovación de TIE de residencia permanente'), ('185', '209'))

    def test_article_191_still_requires_full_text_subject_check(self):
        questions = [
            {'id': 'scope', 'query': 'autorización extraordinaria 2026 ya concedida modificación artículo 191 prórroga excepcional'},
            {'id': 'requirements', 'query': 'regularización extraordinaria continuidad artículo 191 requisitos según vía modificación'},
            {'id': 'steps', 'query': 'regularización extraordinaria 2026 modificación prórroga plazo presentar procedimiento artículo 191'},
        ]
        irrelevant = relevance.provision_relevance('arraigo',
            'Cómo continuar la residencia tras la regularización extraordinaria de 2026',
            'Artículo 191. Disposiciones técnicas sin relación con extranjería.', questions)
        self.assertFalse(irrelevant['relevant'])
        relevant = relevance.provision_relevance('arraigo',
            'Cómo continuar la residencia tras la regularización extraordinaria de 2026',
            'Artículo 191. Modificación de una autorización de residencia temporal por circunstancias excepcionales y arraigo, requisitos y plazo para solicitud de modificación.', questions)
        self.assertTrue(relevant['relevant'])


if __name__ == '__main__':
    unittest.main()
