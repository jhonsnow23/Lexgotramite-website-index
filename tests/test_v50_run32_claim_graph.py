"""Self-contained Run 32 regression tests; no local-upload dependencies."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from legal_claim_graph_v50 import (split_rd316_evidence, build_source_claims,
                                   validate_graph, operative_mechanisms)
from legal_applicability_v50 import build_dossier

TEXT='''10. La autorización concedida tendrá una vigencia de un año por arraigo social. Durante los dos meses previos a su expiración se podrá solicitar una modificación conforme al artículo 191. La presentación de la solicitud prorrogará la validez de la autorización anterior hasta la resolución del procedimiento. Excepcionalmente, si no se pudiera solicitar una modificación, se podrá estudiar la prórroga excepcional bajo las condiciones legales.
[...]
10. La autorización de residencia temporal por circunstancias excepcionales por razón de arraigo extraordinario tendrá una vigencia de un año. Los titulares deberán solicitar una modificación conforme al artículo 191 cuando proceda. La presentación de la solicitud prorrogará la validez de la autorización anterior hasta la resolución del procedimiento. Excepcionalmente, si no se pudiera solicitar una modificación, la autorización podrá prorrogarse si se acreditan los requisitos aplicables.'''


def fixtures():
    ev=[{'evidence_id':'EV_DECREE','source_id':'boe','authority':'boe',
         'official_url':'https://www.boe.es/buscar/doc.php?id=BOE-A-2026-8284',
         'document_title':'Real Decreto 316/2026 — publicación oficial',
         'text':TEXT,'article':None},
        {'evidence_id':'EV_191','source_id':'BOE-A-2024-24099','authority':'boe',
         'official_url':'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099',
         'document_title':'RD 1155/2024','article':'191',
         'text':'Artículo 191. La modificación de autorizaciones temporales por cuenta ajena exige consultar las condiciones de la modalidad. La modificación por cuenta propia exige requisitos que dependen del supuesto concreto.'},
        {'evidence_id':'EV_74','source_id':'BOE-A-2024-24099','authority':'boe',
         'official_url':'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099',
         'document_title':'RD 1155/2024','article':'74',
         'text':'Artículo 74. Los requisitos de una autorización inicial son de carácter específico. Las condiciones se aplican según la remisión normativa.'}]
    plan={'topic':'Continuidad después de la regularización extraordinaria de 2026',
          'commercial_classification':{'business_category':'regularizacion_2026','excluded':False},
          'group':'arraigo'}
    questions=[{'id':'scope','question':'Qué vías de modificación o prórroga existen',
               'status':'PARTIALLY_ANSWERED','evidence_ids':[],'missing_facts':['Verificar condiciones individuales']},
               {'id':'requirements','question':'Qué requisitos de cada procedimiento se aplican',
               'status':'PARTIALLY_ANSWERED','evidence_ids':[],'missing_facts':['Verificar requisitos por vía']},
               {'id':'steps','question':'Cómo presentar una modificación',
               'status':'PARTIALLY_ANSWERED','evidence_ids':[],'missing_facts':['Canal de presentación sin verificar']}]
    return ev,plan,questions


class Run32Tests(unittest.TestCase):
    def test_split_two_distinct_boe_provisions(self):
        ev,_,_=fixtures(); rows=split_rd316_evidence(ev)
        rd=[r for r in rows if r.get('source_id')=='BOE-A-2026-8284']
        self.assertEqual([r['article'] for r in rd],['DA20.10','DA21.10'])
        self.assertNotEqual(rd[0]['evidence_id'],rd[1]['evidence_id'])
        self.assertIn('arraigo extraordinario',rd[1]['text'])

    def test_cannot_fabricate_provision_from_partial_text(self):
        ev,_,_=fixtures();bad={**ev[0],'text':'10. La autorización concedida tendrá una vigencia de un año.'}
        rows=split_rd316_evidence([bad])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['provision_identification'],'UNIDENTIFIED_PROVISION')

    def test_source_claims_are_exact_and_bidirectionally_linked(self):
        ev,plan,questions=fixtures();ev=split_rd316_evidence(ev)
        for q in questions:
            q['evidence_ids']=[e['evidence_id'] for e in ev]
        dossier=build_dossier(plan,ev)
        graph=build_source_claims(ev,dossier,questions)
        self.assertGreater(len(graph['source_claims']),0)
        self.assertEqual(validate_graph(graph,dossier,ev),[])
        self.assertTrue(any(a['supported_claims'] for a in dossier['applicability_evidence']))
        self.assertTrue(all(not link['legal_support_verified'] for link in graph['links']))

    def test_context_only_cannot_supply_sole_claim(self):
        ev,plan,_=fixtures();e=ev[-1]
        # Article 84 is context-only for DA20/DA21 because those origins enable work.
        e={'evidence_id':'EV_84','source_id':'BOE-A-2024-24099','authority':'boe',
           'official_url':'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099',
           'document_title':'RD 1155/2024 artículo 84','article':'84',
           'text':'Artículo 84. Requisitos de autorización inicial de residencia temporal y trabajo por cuenta propia.',
           'research_relevance':{'context_only':True}}
        dossier=build_dossier(plan,[e])
        graph=build_source_claims([e],dossier,[{'id':'requirements','evidence_ids':[e['evidence_id']]}])
        self.assertEqual(graph['source_claims'],[])

    def test_bad_reverse_link_is_rejected(self):
        ev,plan,_=fixtures();dossier=build_dossier(plan,ev)
        dossier['applicability_evidence'][0]['supported_claims']=['CL_FAKE']
        self.assertTrue(validate_graph({'source_claims':[]},dossier,ev))

    def test_two_distinct_mechanisms_per_provision(self):
        ev,_,_=fixtures()
        results=operative_mechanisms(split_rd316_evidence(ev))
        self.assertEqual(len(results),4)
        self.assertEqual({r['mechanism_type'] for r in results},
                         {'EXTENSION_PENDING_MODIFICATION','EXCEPTIONAL_EXTENSION_OF_AUTHORIZATION'})

    def test_execute_creates_graph_and_keeps_partial_block(self):
        import legal_content_v50 as legal
        ev,_,questions=fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);proposal=root/'proposal.json'
            proposal.write_text(json.dumps({'proposals':[{'cluster_id':'seed_regularizacion_2026',
                'proposed_title':'Cómo continuar la residencia tras la regularización extraordinaria de 2026'}]}))
            # Bypass external retrieval and LLM, not the production validation path.
            with patch.object(legal,'plan',return_value={
                      'duplicate_metadata':False,'source_registry_complete':True,'topic':'Postgrant',
                      'commercial_classification':{'business_category':'regularizacion_2026','excluded':False},
                      'group':'arraigo'}),\
                 patch.object(legal,'retrieve_evidence',return_value=(ev,[],{})),\
                 patch.object(legal,'focused_evidence_for_topic',side_effect=lambda x,y:(y,[])),\
                 patch.object(legal,'research_readiness',return_value=(questions,False)):
                rc=legal.execute(proposal,root/'out',retrieval=lambda *a,**kw:None)
            self.assertEqual(rc,2)
            out=root/'out'
            graph=json.loads((out/'source_claim_graph.json').read_text())
            self.assertEqual(len(graph['distinct_legal_mechanisms']),4)
            self.assertEqual(json.loads((out/'decision.json').read_text())['result'],
                             'BLOCKED_INSUFFICIENT_EVIDENCE')
            self.assertFalse((out/'article.json').exists())

    def test_finalize_preserves_legal_block_not_retrieval(self):
        import seo_v50 as seo
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'selection.json').write_text(json.dumps({'selected':{'cluster_id':'seed_regularizacion_2026'}}))
            (folder/'history.json').write_text(json.dumps({'events':[]}))
            (folder/'decision.json').write_text(json.dumps({'result':'BLOCKED_INSUFFICIENT_EVIDENCE'}))
            seo.finalize(SimpleNamespace(output=str(folder),decision=str(folder/'decision.json')))
            summary=json.loads((folder/'run_summary.json').read_text())
            self.assertEqual(summary['result'],'BLOCKED_INSUFFICIENT_EVIDENCE')
            self.assertFalse(summary['publication_allowed'])

if __name__=='__main__':unittest.main()
