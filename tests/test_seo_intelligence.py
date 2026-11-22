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

class SeoV2Tests(unittest.TestCase):
    def test_query_clusters_distinct(self):
        self.assertEqual(seo.cluster_for('cuanto tarda la regularización masiva'), 'regularization_processing')
        self.assertEqual(seo.cluster_for('renovación de residencia en españa'), 'residence_renewal')
        self.assertEqual(seo.cluster_for('renovar autorizacion tras regularizacion'), 'post_regularization_renewal')
        self.assertEqual(seo.cluster_for('jura de nacionalidad'), 'nationality_ceremony')
    def test_competitor_and_location_filter(self):
        self.assertEqual(seo.discard_reason('Lex Sanz extranjería'), 'competitor_name')
        self.assertEqual(seo.discard_reason('abogado extranjeria elgoibar'), 'local_service_unverified')
        self.assertIsNone(seo.discard_reason('renovación residencia en españa'))
    def test_groups_variants_and_prefers_existing_landing(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            root=Path(d)
            (root/'blog').mkdir()
            (root/'blog'/'renovar-residencia-espana.html').write_text('hello',encoding='utf8')
            rows=[
                {'keys':['renovacion residencia en españa','https://lexgotramite.com/blog/renovar-residencia-espana'],'impressions':20,'clicks':1,'position':40},
                {'keys':['renovacion de residencia en españa','https://lexgotramite.com/blog/renovar-residencia-espana'],'impressions':15,'clicks':0,'position':50},
            ]
            result,excluded=seo.cluster_rows(rows,seo.existing_index(root),root)
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]['impressions'],35)
            self.assertEqual(result[0]['query_count'],2)
            self.assertEqual(result[0]['recommended_action'],'improve_existing_page')
            self.assertEqual(result[0]['existing_content_evidence'][0]['path'],'blog/renovar-residencia-espana.html')
            self.assertEqual(excluded,[])
    def test_sparse_without_page_is_monitor(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            result,_=seo.cluster_rows([{'keys':['nacionalidad española por residencia requisitos'],'impressions':2,'position':75}],[],Path(d))
            self.assertEqual(result[0]['recommended_action'],'monitor')
    def test_calendar_no_mutation(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            root=Path(d)
            (root/'blog').mkdir()
            page=root/'blog'/'tipos-de-residencia-en-espana.html'
            page.write_text('original',encoding='utf8')
            rows=[{'keys':['residencia legal en españa','https://lexgotramite.com/blog/tipos-de-residencia-en-espana'],'impressions':100,'position':80}]
            clusters,_=seo.cluster_rows(rows,seo.existing_index(root),root)
            self.assertEqual(len(seo.make_calendar(clusters)),1)
            self.assertEqual(page.read_text(encoding='utf8'),'original')
