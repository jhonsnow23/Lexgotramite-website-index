"""Run 23 regression: missing procedure evidence is not automatically verified."""
import unittest
from scripts import legal_content_v50, official_sources_v50


class ModificationSourcesTests(unittest.TestCase):
    def test_post_grant_modification_sources_discoverable(self):
        rows = official_sources_v50.candidates(
            'Cómo continuar la residencia tras la regularización extraordinaria de 2026',
            'arraigo')
        titles = [title.lower() for _, title, _ in rows]
        self.assertTrue(any('hoja 55' in title for title in titles))
        self.assertTrue(any('ex-26' in title for title in titles))
        self.assertTrue(any('criterio de gestión' in title for title in titles))
        for authority, title, url in rows:
            self.assertTrue(official_sources_v50.allowed(url), title)

    def test_focus_includes_specific_procedure_guidance(self):
        rows = [
            {'evidence_id':'EV_FORM','source_id':'migraciones','authority':'migraciones',
             'document_title':'Formulario EX-26 — solicitud de modificación de residencia o estancia',
             'official_url':'https://inclusion.gob.es/documents/d/migraciones/ex26-formulario-de-solicitud-modificacion-de-autorizacion-de-residencia-o-estancia-editable-1'},
            {'evidence_id':'EV_55','source_id':'migraciones','authority':'migraciones',
             'document_title':'Hoja 55 — modificación desde residencia temporal que habilita a trabajar',
             'official_url':'https://www.inclusion.gob.es/es/web/migraciones/w/55.-modificacion-desde-situaciones-de-autorizaciones-de-residencia-temporal-que-habilitan-a-trabajar'},
            {'evidence_id':'EV_CRITERIO','source_id':'migraciones','authority':'migraciones',
             'document_title':'Criterio de gestión DGGMR 1/2025 — modificación y prórroga según artículo 191',
             'official_url':'https://www.inclusion.gob.es/documents/d/migraciones/criterio-de-gestion-dggm_rloex-1-2025_modificaciones-estancias-y-residencias-y-prorrogas-arraigos'},
            {'evidence_id':'EV_INITIAL','source_id':'migraciones','authority':'migraciones',
             'document_title':'Requisitos para solicitar regularización inicial',
             'official_url':'https://www.inclusion.gob.es/web/migraciones/regularizacion-inicial'}
        ]
        plan={'topic':'Cómo continuar la residencia tras la regularización extraordinaria de 2026',
              'group':'arraigo','commercial_classification':{'business_category':'regularizacion_2026'}}
        selected, excluded = legal_content_v50.focused_evidence_for_topic(plan,rows)
        self.assertEqual({r['evidence_id'] for r in selected}, {'EV_FORM','EV_55','EV_CRITERIO'})
        self.assertEqual([r['evidence_id'] for r in excluded], ['EV_INITIAL'])

    def test_no_change_to_publication_gate(self):
        from pathlib import Path
        self.assertIn("'publication_allowed':False", Path(legal_content_v50.__file__).read_text(encoding='utf-8'))

if __name__ == '__main__':
    unittest.main()
