import copy,json,unittest
from pathlib import Path
from unittest.mock import Mock
from test_v50_run35_branch_applicability import legal
from editorial_scope_v50 import alternative_scope, REVIEW_FIELDS, passage_route_compatibility
F=json.loads((Path(__file__).parent/'fixtures/run45_replay.json').read_text())
class Run46Tests(unittest.TestCase):
    def run_scope(self,*responses,limit=1):
        coverage=copy.deepcopy(F['coverage']); report={}; call=Mock(side_effect=responses)
        result=alternative_scope(F['plan'],coverage,F['evidence'],legal.build_dossier(F['plan'],F['evidence']),call=call,model='gpt-4.1-mini',client=None,report=report,max_proposals=limit)
        self.assertEqual(coverage,F['coverage']); self.assertFalse(report['publication_allowed']); return result,report,call
    def verdict(self,approved=True):
        return {**{k:approved for k in REVIEW_FIELDS},'supported_question_indices':list(range(len(F['proposal']['questions']))),'reasons':['Simulated review only']}
    def test_actual_proposal_reaches_review(self):
        result,r,c=self.run_scope(F['proposal'],self.verdict()); self.assertIsNotNone(result,r.get('reason')); self.assertEqual(c.call_count,2); self.assertEqual(len(r['shared_passage_uses']),4)
        self.assertIn('P002',r['eligible_passage_aliases']); self.assertIn('P003',r['eligible_passage_aliases'])
    def test_veto(self):
        result,r,c=self.run_scope(F['proposal'],self.verdict(False)); self.assertIsNone(result); self.assertEqual(r['reason'],'INDEPENDENT_SCOPE_REJECTED')
    def test_no_generic_inheritance(self):
        record={'document_reference':'BOE-A-2026-8284','article_reference':'DA20.10','applicability':'CONDITIONALLY_APPLICABLE','route_ids':['MODIFICACION_ART_191']}
        route='MOD_ART191_2_AJENA_LT_1Y'; self.assertEqual(passage_route_compatibility(record,route),'SHARED_ORIGIN_MODIFICATION_RULE')
        for change in ({'document_reference':'other'},{'article_reference':'DA20.9'},{'applicability':'CONTEXT_ONLY'},{'route_ids':['MOD_ART191_3_AJENA_GE_1Y']}): self.assertIsNone(passage_route_compatibility({**record,**change},route))
        self.assertIsNone(passage_route_compatibility(record,'MOD_CUENTA_PROPIA_LT_1Y_UNRESOLVED'))
    def test_wrong_route_retries(self):
        from evidence_passages_v50 import build_catalog,select_context,short_passage_context
        dossier=legal.build_dossier(F['plan'],F['evidence']); selected,_=select_context(build_catalog(F['evidence']),F['evidence'],dossier); aliases,_=short_passage_context(selected)
        wrong=next(a for a,p in zip(aliases,selected) if p['article_reference']=='80')
        p=copy.deepcopy(F['proposal']); p['questions'][0]['passage_ids']=[wrong];p['title']+=': información'
        result,r,c=self.run_scope(p,F['proposal'],self.verdict(),limit=2); self.assertIsNotNone(result,r.get('reason')); self.assertEqual(r['attempts'][0]['reason'],'PASSAGE_WRONG_ROUTE'); self.assertNotIn(wrong,r['attempts'][0]['eligible_passage_aliases']); self.assertEqual(c.call_count,3)
