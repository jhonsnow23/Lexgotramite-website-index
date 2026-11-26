import copy
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock
from test_v50_run35_branch_applicability import legal
from temporary_residence_policy_v50 import classify, SEEDS
from editorial_scope_v50 import alternative_scope, commercial_scope_check, selectable_routes
from evidence_passages_v50 import build_catalog, select_context, short_passage_context
from seo_v50 import topic_blocker

F=json.loads((Path(__file__).parent/'fixtures/run41_replay.json').read_text())

class Run42Tests(unittest.TestCase):
    def setUp(self):
        self.plan=F['plan']; self.covered=F['coverage']; self.e=F['evidence']
        self.d=legal.build_dossier(self.plan,self.e)
        self.report={}
    def run_scope(self,responses,**kwargs):
        m=Mock(side_effect=responses)
        result=alternative_scope(self.plan,self.covered,self.e,self.d,call=m,model='test',client=None,report=self.report,**kwargs)
        return result,m
    def narrow(self):
        # Construct a controlled alternative against the *actual* run 41 catalog.
        from test_v50_run39_passages_scope import Run39Tests as ReplayHelper
        h=ReplayHelper(); h.setUp(); p=h.proposal(['requirements:0'])
        cat=build_catalog(self.e); selected,_=select_context(cat,self.e,self.d)
        aliases,_=short_passage_context(selected); reverse={v:k for k,v in aliases.items()}
        for q,article in zip(p['questions'],('191','74')):
            pid=next(x['passage_id'] for x in selected if x['article_reference']==article and not x['parent_passage_id'])
            q['passage_ids']=[reverse[pid]]
        return p,h.verdict()
    def test_exact_run41_title_passes_commercial_gate(self):
        self.assertEqual(classify(F['proposal']['title'])['business_category'],'regularizacion_2026')
        self.assertTrue(commercial_scope_check(self.plan,F['proposal'])['accepted'])
    def test_variants_and_excluded_topics(self):
        for title in ('Modificación de autorización extraordinaria 2026', 'Prórroga de la autorización extraordinaria de 2026', 'Modificar autorización extraordinaria de residencia y trabajo concedida en 2026'):
            self.assertEqual(classify(title)['business_category'],'regularizacion_2026',title)
        for title in ('Cómo solicitar autorización extraordinaria 2026', 'Renovación TIE autorización extraordinaria 2026', 'Nacionalidad tras la autorización extraordinaria 2026', 'Modificación a residencia permanente tras la autorización extraordinaria 2026', 'Autorización extraordinaria 2026','Solicitud de la autorización extraordinaria 2026 y modificación'):
            self.assertTrue(classify(title)['excluded'],title)
        for cat,seed in SEEDS.items():self.assertEqual(classify(seed['proposed_title'])['business_category'],cat)
    def test_context_fallback_and_mismatches(self):
        p={**F['proposal'],'title':'Modificación de residencia: requisitos del artículo 191'}
        self.assertTrue(commercial_scope_check(self.plan,p)['accepted'])
        for title in ('Renovación del pasaporte','Nacionalidad española','Renovación residencia no lucrativa','Cómo solicitar la regularización extraordinaria de 2026'):
            self.assertFalse(commercial_scope_check(self.plan,{**p,'title':title})['accepted'],title)
        self.assertFalse(commercial_scope_check(self.plan,{**p,'business_category':'arraigo'})['accepted'])
        self.assertFalse(commercial_scope_check(self.plan,{**p,'search_intent':'Nacionalidad española'})['accepted'])
    def test_real_run41_forbidden_branch_is_rejected_before_review(self):
        result,m=self.run_scope([F['proposal']],max_proposals=1)
        self.assertIsNone(result); self.assertEqual(m.call_count,1)
        self.assertEqual(self.report['reason'],'FORBIDDEN_ROUTE_IDS')
        self.assertEqual(self.report['forbidden_route_ids'],['MOD_CUENTA_PROPIA_LT_1Y_UNRESOLVED'])
        self.assertTrue(self.report['commercial_scope_check']['accepted'])
        props=m.call_args.kwargs['response_format']['json_schema']['schema']['properties']
        enums=props['questions']['items']['properties']['route_ids']['items']['enum']
        self.assertEqual(set(enums),selectable_routes(self.d))
        self.assertNotIn('MOD_CUENTA_PROPIA_LT_1Y_UNRESOLVED',enums)
        self.assertNotIn('MOD_ART191_4_ORIGIN_NO_WORK',enums)
        self.assertFalse(self.report['publication_allowed'])
    def test_retry_real_proposal_then_narrow_scope_and_independent_review(self):
        p,verdict=self.narrow(); original=copy.deepcopy(self.covered)
        result,m=self.run_scope([F['proposal'],p,verdict])
        self.assertIsNotNone(result,self.report.get('reason')); self.assertEqual(m.call_count,3)
        self.assertEqual(self.report['attempts'][0]['reason'],'FORBIDDEN_ROUTE_IDS')
        self.assertEqual(self.report['status'],'APPROVED_FOR_DRAFT_ONLY')
        payload=json.loads(m.call_args_list[1].args[0][1]['content'])
        self.assertEqual(payload['previous_rejections'][0]['reason'],'FORBIDDEN_ROUTE_IDS')
        self.assertEqual(self.covered,original); self.assertFalse(self.report['publication_allowed'])
    def test_review_veto_then_retry_and_bounded_exhaustion(self):
        p,v=self.narrow(); veto={**v,'approved':False}
        p2={**p,'title':p['title']+' — condiciones específicas','scope':p['scope']+' (second)'}
        result,m=self.run_scope([p,veto,p2,v])
        self.assertIsNotNone(result);self.assertEqual(m.call_count,4)
        self.assertEqual(self.report['attempts'][0]['reason'],'INDEPENDENT_SCOPE_REJECTED')
        result,m=self.run_scope([F['proposal']]*3,max_proposals=9)
        self.assertIsNone(result);self.assertEqual(m.call_count,3)
        self.assertEqual(len(self.report['attempts']),3);self.assertEqual(self.report['max_proposals'],3)
        self.assertEqual(self.report['reason'],'REPEATED_PROPOSAL')
    def test_transport_error_never_approves_or_retries(self):
        result,m=self.run_scope([RuntimeError('simulated API error')])
        self.assertIsNone(result);self.assertEqual(m.call_count,1);self.assertFalse(self.report['publication_allowed'])
    def test_topic_rotation_after_repeated_legal_blockage(self):
        item={'cluster_id':'seed_regularizacion_2026'}
        h=[{'cluster_id':item['cluster_id'],'date':d,'status':'BLOCKED_INSUFFICIENT_EVIDENCE'} for d in ('2026-11-24','2026-11-25')]
        today=date(2026,11,26)
        self.assertIn('rotate',topic_blocker(item,h,today))
        self.assertIsNone(topic_blocker(item,h,today,ignore_attempt_backoff=True))
        self.assertIsNone(topic_blocker({'cluster_id':'seed_arraigo'},h,today))
        self.assertIsNone(topic_blocker(item,h,date(2026,12,3)))
