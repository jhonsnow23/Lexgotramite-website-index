import importlib.util
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[1] / 'scripts' / 'seo_intelligence.py'
spec = importlib.util.spec_from_file_location('seo_intelligence', SRC)
seo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seo)

class SeoTests(unittest.TestCase):
    def test_accent_and_slug(self):
        self.assertEqual(seo.slugify('Nacionalidad española por residencia'), 'nacionalidad-espanola-por-residencia')
    def test_topics(self):
        self.assertEqual(seo.topic_for('¿Cómo renovar mi autorización?'), 'post_regularization')
        self.assertEqual(seo.topic_for('Jura de nacionalidad'), 'nationality')
    def test_aggregates_weighted_position_and_ctr(self):
        rows = [
            {'keys':['nacionalidad por residencia','https://lexgotramite.com/a'], 'impressions':90,'clicks':9,'position':10},
            {'keys':['nacionalidad por residencia','https://lexgotramite.com/b'], 'impressions':10,'clicks':1,'position':20},
        ]
        result = seo.analyze(rows, slugs=set())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['impressions'],100)
        self.assertEqual(result[0]['ctr'], .1)
        self.assertEqual(result[0]['average_position'],11)
        self.assertTrue(result[0]['legal_review_required'])
    def test_dedupe(self):
        rows = [{'keys':['nacionalidad por residencia'], 'impressions':10,'position':5}]
        self.assertEqual(seo.analyze(rows, {'nacionalidad-por-residencia'})[0]['recommended_action'],'review_existing')
    def test_unrelated_filtered(self):
        self.assertEqual(seo.analyze([{'keys':['weather london'],'impressions':20}]),[])

if __name__ == '__main__': unittest.main()
