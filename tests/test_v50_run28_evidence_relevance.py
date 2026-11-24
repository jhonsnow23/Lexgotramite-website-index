"""Run 28 regression: post-grant evidence must not be diluted by initial FAQs."""
import unittest
from scripts import legal_content_v50 as legal, official_sources_v50 as sources

class Run28EvidenceRelevance(unittest.TestCase):
    def test_initial_100_questions_not_used_as_continuity_evidence(self):
        plan = {'topic':'Cómo continuar residencia tras regularización extraordinaria de 2026',
                'commercial_classification':{'business_category':'regularizacion_2026'}}
        def source(title, url):
            return {'source_id':'migraciones','authority':'migraciones',
                    'evidence_id':title,'document_title':title,'official_url':url}
        rows=[source('Ministerio: 100 preguntas técnicas de regularización',
                     'https://inclusion.gob.es/documents/100%20Preguntas%20técnicas.pdf'),
              source('Ministerio: preguntas sobre modificación o prórroga tras la regularización',
                     'https://inclusion.gob.es/documents/Preguntas%20y%20respuestas.pdf')]
        selected,excluded=legal.focused_evidence_for_topic(plan,rows)
        self.assertEqual([r['evidence_id'] for r in selected],[rows[1]['evidence_id']])
        self.assertEqual(len(excluded),1)

    def test_criterion_prioritizes_191_2_191_3_not_unrelated_191_8(self):
        body=('Inicio '+('x'*300)+' artículo 191.2: condiciones de modificación por cuenta ajena. '
              +(' y '*8000)+' artículo 191.8: familiares de ciudadano de la Unión. '
              +(' z '*8000)+' artículo 191.3: cambio de autorización tras un año. ')
        result=sources.excerpt_for_article_191_criterion(body,limit=4000)
        self.assertIn('artículo 191.2',result)
        self.assertIn('artículo 191.3',result)
        self.assertNotIn('artículo 191.8',result)

    def test_normal_sources_still_use_standard_extractor(self):
        text='39. ¿Qué hacer? La respuesta sobre modificación tras caducidad. '
        self.assertEqual(sources.excerpt_for_procedure_guidance(text),text[:1200])

if __name__ == '__main__': unittest.main()
