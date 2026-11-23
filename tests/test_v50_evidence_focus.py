"""Deterministic evidence selection regression; no network and no legal certification."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from legal_content_v50 import focused_evidence_for_topic

class FocusTests(unittest.TestCase):
    def test_permanent_residence_filters_other_renewal_rules(self):
        rows = [
            {'evidence_id':'a','authority':'boe','source_id':'BOE-A-2024-24099','article':'71'},
            {'evidence_id':'b','authority':'boe','source_id':'BOE-A-2024-24099','article':'112'},
            {'evidence_id':'c','authority':'boe','source_id':'BOE-A-2024-24099','article':'185'},
            {'evidence_id':'d','authority':'boe','source_id':'BOE-A-2024-24099','article':'209'},
            {'evidence_id':'e','authority':'migraciones','official_url':'https://www.inclusion.gob.es/web/migraciones/w/49.-autorizacion-de-residencia-de-larga-duracion-nacional'},
            {'evidence_id':'f','authority':'policia','official_url':'https://sede.policia.gob.es/portalCiudadano/_es/tramites_extranjeria_tramite_tarjetaresidencia_largaduracion.php'},
        ]
        selected,excluded=focused_evidence_for_topic({'group':'renewal','topic':'Renovación de residencia permanente'},rows)
        self.assertEqual([r['evidence_id'] for r in selected], ['c','d','e','f'])
        self.assertEqual([r['evidence_id'] for r in excluded], ['a','b'])
    def test_not_applied_to_other_renewal_topics(self):
        rows=[{'evidence_id':'a','article':'71'}]
        self.assertEqual(focused_evidence_for_topic({'group':'renewal','topic':'Renovación reagrupación familiar'},rows),(rows,[]))
    def test_do_not_promote_non_target_boe_article(self):
        rows=[{'evidence_id':'a','authority':'boe','source_id':'BOE-A-2024-24099','article':'71','text':'tarjeta larga duración'}]
        selected,excluded=focused_evidence_for_topic({'group':'renewal','topic':'Renovación de residencia permanente'},rows)
        self.assertEqual(selected,[])
        self.assertEqual(len(excluded),1)
if __name__=='__main__':unittest.main()
