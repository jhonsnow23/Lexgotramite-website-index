"""Run 34: trace both legal mechanisms, without certifying applicability."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from legal_claim_graph_v50 import build_source_claims,validate_graph

class RouteEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.evidence=[{'evidence_id':'EV_DA','text':(
            'Los titulares podrán solicitar una modificación conforme al artículo 191 de este reglamento. '
            'La presentación de la solicitud prorrogará la validez de la autorización anterior hasta la resolución del procedimiento. '
            'Excepcionalmente, si no se pudiera solicitar una modificación conforme a este reglamento, '
            'esta autorización podrá ser prorrogada siempre y cuando se acredite estar en búsqueda activa de empleo.'),
            'article':'DA21.10','provision':'Disposición adicional vigesimoprimera, apartado 10'}]
        self.dossier={'applicability_evidence':[{'evidence_id':'EV_DA',
            'applicability':'CONDITIONALLY_APPLICABLE',
            'destination_authorization':['MODIFICACION_ART_191','PRORROGA_EXCEPCIONAL'],
            'applicability_conditions':['Verificar condiciones individuales'],
            'supported_claims':[],'verification_status':'UNVERIFIED_APPLICABILITY'}]}
    def test_scope_has_both_routes_with_exact_provenance(self):
        graph=build_source_claims(self.evidence,self.dossier,[{'id':'scope','evidence_ids':['EV_DA']}])
        routes=[r['procedure_routes'] for r in graph['source_claims']]
        self.assertIn(['MODIFICACION_ART_191'],routes)
        self.assertIn(['PRORROGA_EXCEPCIONAL'],routes)
        self.assertEqual(validate_graph(graph,self.dossier,self.evidence),[])
        self.assertTrue(all(not x['legal_support_verified'] for x in graph['links']))
    def test_requirements_does_not_lose_exceptional_route(self):
        graph=build_source_claims(self.evidence,self.dossier,[{'id':'requirements','evidence_ids':['EV_DA']}])
        self.assertIn(['PRORROGA_EXCEPCIONAL'],[r['procedure_routes'] for r in graph['source_claims']])
    def test_no_evidence_id_no_claims(self):
        graph=build_source_claims(self.evidence,self.dossier,[{'id':'scope','evidence_ids':['EV_NOT_REAL']}])
        self.assertFalse(graph['source_claims'])

if __name__=='__main__':unittest.main()
