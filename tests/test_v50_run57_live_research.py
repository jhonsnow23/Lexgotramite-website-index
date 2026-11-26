"""Replay live Run56 research; reviewer and XML tests are explicitly simulated."""
import copy,json,tempfile,unittest,xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from test_v50_run55_first_article import engine, response, verdict, proposed, ArchivedResearch
from test_boe_universal_v45 import Response

F=json.loads((Path(__file__).parent/'fixtures/run56_live_replay.json').read_text())
N='topic_01_no_lucrativa/'
S='topic_02_cuenta_propia/'

class LiveArchivedResearch(ArchivedResearch):
    def article(self, document, article):
        self.ledger.document(f'{document}:{article}')
        return copy.deepcopy([r for r in F[N+'evidence.json'] if r['source_id']==document and r.get('article')==str(article)])
    def guidance(self, category, topic):
        return copy.deepcopy([r for r in F[N+'evidence.json'] if r['authority']=='migraciones'])

class Run57(unittest.TestCase):
    def test_actual_live_response_blank_exceptions_and_citations(self):
        raw=F[N+'research_round_01.json']; evidence=F[N+'evidence.json']
        plan=engine.legacy.plan({'proposals':[{'proposed_title':engine.PROFILES['no_lucrativa'][0]}]})
        cat,dossier,aliases,rows=engine.source_context(evidence,plan)
        self.assertEqual(aliases,F[N+'passage_aliases.json'])
        self.assertEqual(raw['claims'][0]['exceptions'],'')
        claims,gaps=engine.validate_research(raw,aliases,cat,evidence,dossier)
        self.assertEqual(len(claims),3); self.assertTrue(any(g['blocking'] for g in gaps))
        self.assertEqual(rows[0]['retrieved_at'],evidence[0]['retrieved_at'])
        self.assertIsNone(rows[0]['document_metadata']) # no invented live metadata
        self.assertRaises(engine.IntegrityError,engine.plain,'https://bad.example',allow_empty=True)
        self.assertRaises(engine.IntegrityError,engine.plain,'')

    def test_actual_cuenta_propia_blank_exception(self):
        evidence=F[S+'evidence.json']; raw=F[S+'research_round_01.json']
        plan=engine.legacy.plan({'proposals':[{'proposed_title':engine.PROFILES['cuenta_propia'][0]}]})
        cat,dossier,aliases,_=engine.source_context(evidence,plan)
        claims,gaps=engine.validate_research(raw,aliases,cat,evidence,dossier)
        self.assertGreaterEqual(len(claims),2)

    def test_scoped_index_ambiguity_fails_only_requested_article(self):
        xml=ET.fromstring('<r><bloque id="a1" titulo="Art 1"/><bloque id="other1" titulo="Art 1"/><bloque id="real52" titulo="Art 52"/></r>')
        with self.assertRaisesRegex(engine.boe.BOEError,'AMBIGUOUS_INDEX'): engine.boe.index_map(xml)
        self.assertEqual(engine.boe.index_map(xml,requested_articles=[52]),{(52,''):'real52'})
        with self.assertRaisesRegex(engine.boe.BOEError,'AMBIGUOUS_INDEX'): engine.boe.index_map(xml,requested_articles=[1])
        self.assertEqual(engine.boe.index_map(xml,requested_articles=[32]),{})

    def test_metadata_and_versions_from_xml_not_invented(self):
        idx=b'<r><bloque id="x1" titulo="Art 1"/><bloque id="y1" titulo="Art 1"/><bloque id="a52" titulo="Art 52"/></r>'
        block=b'<r><version fecha_publicacion="20000112"><p>Art 52. Texto anterior completo de prueba con suficiente longitud.</p></version><version fecha_publicacion="20250101" fecha_vigencia="20250201"><p>Art 52. Texto de prueba vigente para verificar el tratamiento de versiones.</p></version></r>'
        meta=b'<r><metadatos><identificador>BOE-A-2000-544</identificador><fecha_actualizacion>20250102T000000Z</fecha_actualizacion><fecha_vigencia>20000201</fecha_vigencia><estado_consolidacion>Consolidado</estado_consolidacion></metadatos></r>'
        seen=[]
        def opener(req,timeout):
            url=req.full_url;seen.append(url)
            return Response(url,idx if url.endswith('/indice') else meta if url.endswith('/metadatos') else block)
        with tempfile.TemporaryDirectory() as t:
            r=engine.OfficialResearch(engine.Ledger(engine.Limits(),Path(t)));r.opener=opener
            row=r.article(engine.LO,52)[0]
            self.assertEqual(row['version_date'],'2025-02-01');self.assertEqual(row['version_date_basis'],'fecha_vigencia')
            self.assertEqual(row['available_version_dates'],['2000-01-12','2025-02-01'])
            self.assertEqual(row['document_metadata']['fecha_actualizacion'],'20250102T000000Z')
            self.assertEqual(row['legal_status'],'UNVERIFIED')
            self.assertEqual(r.article(engine.LO,52)[0],row);self.assertEqual(len(seen),3)

    def test_explicit_adverse_metadata_blocks_claim(self):
        evidence=copy.deepcopy(F[N+'evidence.json']); raw=F[N+'research_round_01.json']
        evidence[0]['selected_as_of']='2026-11-26'
        for fields in ({'fecha_derogacion':'20260101'},{'fecha_vigencia':'20270101'},{'estado_consolidacion':'Desactualizado'}):
            evidence[0]['document_metadata']={'status':'RETRIEVED',**fields}
            plan=engine.legacy.plan({'proposals':[{'proposed_title':engine.PROFILES['no_lucrativa'][0]}]})
            cat,dossier,aliases,_=engine.source_context(evidence,plan)
            with self.assertRaisesRegex(engine.IntegrityError,'adverse document metadata'):
                engine.validate_research(raw,aliases,cat,evidence,dossier)

    def run_replay(self,resolve):
        seen=[]
        def transport(payload):
            data=json.loads(payload['input']); stage=payload['text']['format']['name'];seen.append(stage)
            if stage=='research':
                raw=copy.deepcopy(F[N+'research_round_02.json'])
                # Preserve actual live claims and gap classifications unchanged.
            else:
                self.assertIn('CANDIDATO INTERNO NO APROBADO',data['rendered_markdown'])
                self.assertEqual(len(data['blocking_gaps']),2)
                raw=verdict(data,approved=resolve)
                raw['blocking_gap_checks']=[{'gap_id':g['gap_id'],'resolution':'RESOLVED_BY_EVIDENCE' if resolve else 'STILL_BLOCKING',
                    'reason':'Simulated gap check only, not a live legal assessment.', 'passage_ids':['P001']} for g in data['blocking_gaps']]
            return response(raw,payload['model'])
        with tempfile.TemporaryDirectory() as t:
            r=engine.run(t,category='no_lucrativa',transport=transport,researcher_factory=LiveArchivedResearch,
                limits=engine.Limits(topics=1,research_rounds=1,draft_repairs=0))
            self.assertEqual(seen,['research','legal_review'])
            self.assertEqual(r['candidate_articles_generated'],1)
            self.assertEqual(r['articles_independently_approved'],0)
            self.assertFalse(r['publication_allowed']);self.assertTrue(r['simulated'])
            self.assertTrue((Path(t)/N/'candidates/01/candidate.md').exists())
            self.assertFalse((Path(t)/N/'article.md').exists())
            return r

    def test_real_claims_reach_private_draft_review_veto_remains(self):
        self.assertEqual(self.run_replay(False)['result'],'BLOCKED_LEGAL_VALIDATION')

    def test_simulated_gap_resolution_never_real_approval(self):
        self.assertEqual(self.run_replay(True)['result'],'SIMULATED_REVIEW_PASS')

    def test_gap_resolution_requires_all_unique_grounded_checks(self):
        gaps=[{'gap_id':'G001'},{'gap_id':'G002'}]; aliases={'P001':'canonical'}
        c={'gap_id':'G001','resolution':'RESOLVED_BY_EVIDENCE','reason':'Grounded','passage_ids':['P001']}
        d={**c,'gap_id':'G002'}
        for checks in ([c], [c,c], [c,{**d,'passage_ids':['P999']}], [c,{**d,'resolution':'STILL_BLOCKING'}], [c,{**d,'reason':''}]):
            self.assertFalse(engine.blocking_gap_checks_pass({'blocking_gap_checks':checks},gaps,aliases))
        self.assertTrue(engine.blocking_gap_checks_pass({'blocking_gap_checks':[c,d]},gaps,aliases))
