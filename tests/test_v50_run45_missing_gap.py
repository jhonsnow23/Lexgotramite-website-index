"""Replay Run 44's incomplete coverage judgment without certifying missing law."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from test_v50_run35_branch_applicability import legal
from editorial_scope_v50 import alternative_scope, REVIEW_FIELDS
from evidence_passages_v50 import build_catalog, select_context, short_passage_context

F = json.loads((Path(__file__).parent/'fixtures/run44_replay.json').read_text())

class Run45Tests(unittest.TestCase):
    def setUp(self):
        self.e = F['evidence']; self.plan = F['research_plan']
        self.original = F['research_coverage']['questions']
        self.d = legal.build_dossier(self.plan, self.e)
        ids = {r['evidence_id']:f'R{i:03d}' for i,r in enumerate(self.e,1)}
        self.judgments = {'questions':[{**q,'evidence_ids':[ids[x] for x in q['evidence_ids']]} for q in self.original]}

    def coverage(self):
        with patch.object(legal,'call_model',return_value=self.judgments) as call:
            covered,ready=legal.research_readiness(self.plan,self.e,dossier=self.d)
        self.assertEqual(call.call_count,1)
        self.assertFalse(ready)
        return covered

    def proposal(self, covered):
        catalog=build_catalog(self.e); selected,_=select_context(catalog,self.e,self.d)
        aliases,_=short_passage_context(selected); reverse={v:k for k,v in aliases.items()}
        route='MOD_ART191_2_AJENA_LT_1Y'
        return {'title':'Modificación por cuenta ajena tras la regularización extraordinaria de 2026: condiciones antes del año',
                'search_intent':'Continuidad por cuenta ajena antes del año','business_category':'regularizacion_2026',
                'scope':'Synthetic narrow scope for control-flow regression', 'utility':'Synthetic utility',
                'seo_rationale':'Synthetic intent match','omission_rationale':'Synthetic rationale requiring independent review',
                'excluded_gap_ids':[f'{q["id"]}:{i}' for q in covered for i,_ in enumerate(q.get('blocking_missing_facts',[]))],
                'limitations':['No inference about other routes'],'individual_conditions':['Individual eligibility must be assessed'],
                'questions':[{'question':f'Pregunta de prueba {a}','answer':'Synthetic answer, not legal guidance',
                              'route_ids':[route],'passage_ids':[reverse[next(x['passage_id'] for x in selected if x['article_reference']==a and not x['parent_passage_id'])]]} for a in ('191','74')]}

    def verdict(self,approved):
        return {**{k:approved for k in REVIEW_FIELDS if k not in ('supported_question_indices','reasons')},'supported_question_indices':[0,1],'reasons':['Simulated independent decision']}

    def test_actual_missing_facts_preserved_and_matrix_gap_restored(self):
        covered=self.coverage(); q=covered[1]
        self.assertEqual(q['status'],'PARTIALLY_ANSWERED'); self.assertEqual(q['missing_facts'],[])
        self.assertEqual(q['reason'],self.original[1]['reason'])
        self.assertEqual(q['gap_assessments'][0]['classification'],'MATERIAL')
        self.assertEqual(q['gap_assessments'][0]['origin'],'APPLICABILITY_MATRIX')
        self.assertIn(q['gap_assessments'][0]['missing_fact'],q['blocking_missing_facts'])
        for row in covered[1:]:
            self.assertEqual(row['draft_readiness'],'BLOCKED')
            self.assertIn('Partial research without explicit missing facts',row['blocking_missing_facts'])
            self.assertEqual(row['gap_diagnostics']['skip_reason'],'INCOMPLETE_JUDGMENT_WITHOUT_MISSING_FACTS')

    def test_replay_reaches_independent_review_and_veto_still_blocks(self):
        covered=self.coverage(); original=copy.deepcopy(covered)
        for approved in (False,True):
            call=Mock(side_effect=[self.proposal(covered),self.verdict(approved)]); report={}
            result=alternative_scope(self.plan,covered,self.e,self.d,call=call,model='gpt-4.1-mini',client=None,report=report,max_proposals=1)
            self.assertEqual(call.call_count,2,report.get('reason'))
            self.assertEqual(result is not None,approved,report.get('reason'))
            self.assertFalse(report['publication_allowed']);self.assertEqual(covered,original)
            self.assertEqual(report['status'],'APPROVED_FOR_DRAFT_ONLY' if approved else 'REJECTED')

    def test_generic_format_gap_alone_cannot_trigger_scope(self):
        covered=self.coverage(); covered[1]['gap_assessments']=[]
        report={}; call=Mock()
        result=alternative_scope(self.plan,covered,self.e,self.d,call=call,model='test',client=None,report=report)
        self.assertIsNone(result);call.assert_not_called();self.assertEqual(report['status'],'NO_RECORDED_MATERIAL_GAP')

    def test_no_citations_does_not_create_material_assessment(self):
        self.judgments['questions'][1]['evidence_ids']=[]
        covered=self.coverage();self.assertEqual(covered[1]['gap_assessments'],[])
        self.assertIn('No valid evidence citations for this question',covered[1]['blocking_missing_facts'])

    def test_full_execution_reviewer_veto_preserves_original_coverage(self):
        covered=self.coverage();responses=[self.judgments,self.proposal(covered),self.verdict(False)]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'proposal.json').write_text('{}')
            with patch.object(legal,'plan',return_value=self.plan),patch.object(legal,'retrieve_evidence',return_value=(self.e,[],{})),patch.object(legal,'focused_evidence_for_topic',side_effect=lambda p,e:(e,[])),patch.object(legal,'call_model',side_effect=responses) as call:
                rc=legal.execute(p/'proposal.json',p/'out',max_revisions=0,max_scope_proposals=1)
            out=p/'out'; decision=json.loads((out/'decision.json').read_text());scope=json.loads((out/'editorial_scope_decision.json').read_text());research=json.loads((out/'research_coverage.json').read_text())
            self.assertEqual(rc,2,decision);self.assertEqual(call.call_count,3);self.assertFalse(decision['publication_allowed']);self.assertFalse(research['ready']);self.assertEqual(scope['reason'],'INDEPENDENT_SCOPE_REJECTED');self.assertFalse((out/'article.json').exists())
