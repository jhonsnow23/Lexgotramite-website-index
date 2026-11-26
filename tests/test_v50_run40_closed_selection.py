import json
import unittest
from pathlib import Path
from unittest.mock import patch
from test_v50_run35_branch_applicability import legal
from evidence_passages_v50 import build_catalog, select_context, short_passage_context

F=json.loads((Path(__file__).parent/'fixtures/run39_replay.json').read_text())
class Run40Tests(unittest.TestCase):
    def setUp(self):
        self.e=F['evidence']; self.plan=F['research_plan']; self.q=F['research_coverage']['questions'][2]
        self.d=legal.build_dossier(self.plan,self.e); self.b=legal.general_guidance_branch_coverage(self.e,self.d)
        self.catalog=build_catalog(self.e); self.selected,_=select_context(self.catalog,self.e,self.d)
        self.aliases,self.short=short_passage_context(self.selected)
        self.old=F['gap_assessment_diagnostics']['questions'][2]['diagnostics']['attempts'][0]['parsed_response']
    def assess(self,i):
        return {'index':i,'classification':'OPTIONAL_DETAIL','reason':'Synthetic test only','retained_answer':'Synthetic bounded answer','limitation':'No universal checklist','supporting_passage_ids':[next(iter(self.aliases))]}
    def run_assess(self,*outputs):
        with patch.object(legal,'call_model',side_effect=outputs) as m:
            r=legal._general_guidance_missing_fact_classification(self.q,self.b,plan=self.plan,evidence=self.e,dossier=self.d,model='test',client=None)
        return r,m
    def test_actual_invalid_ids_retry_then_resolve(self):
        r,m=self.run_assess(self.old,{'assessments':[self.assess(0),self.assess(1)]})
        self.assertEqual(m.call_count,2); self.assertFalse(r['blocking_missing_facts'])
        self.assertEqual(len(r['gap_assessments']),2)
        pid=next(iter(self.aliases.values())); self.assertEqual(r['gap_assessments'][0]['supporting_passages'][0]['quote'],self.catalog['passages'][pid]['verbatim_text'])
        props=m.call_args.kwargs['response_format']['json_schema']['schema']['properties']['assessments']['items']['properties']
        self.assertNotIn('evidence_ids',props); self.assertEqual(props['supporting_passage_ids']['items']['enum'],list(self.aliases))
        self.assertEqual(props['index']['enum'],[0,1]); self.assertEqual(r['gap_diagnostics']['attempts'][0]['selection_retry'],'ALL_NONMATERIAL_SELECTIONS_INVALID')
    def test_actual_invalid_ids_stay_blocking_after_retry(self):
        r,m=self.run_assess(self.old,self.old)
        self.assertEqual(m.call_count,2); self.assertEqual(len(r['blocking_missing_facts']),2)
        self.assertEqual([x['reason'] for x in r['gap_diagnostics']['rejected']],['INVALID_SUPPORTING_PASSAGE']*2)
    def test_retry_error_retains_original_invalid_diagnostics(self):
        r,m=self.run_assess(self.old,RuntimeError('simulated'))
        self.assertEqual(m.call_count,2); self.assertEqual(len(r['blocking_missing_facts']),2)
        self.assertEqual(r['gap_diagnostics']['attempts'][1]['status'],'CALL_ERROR')
    def test_material_preserved_and_other_row_valid(self):
        a={**self.assess(0),'classification':'MATERIAL','supporting_passage_ids':[]}
        r,m=self.run_assess({'assessments':[a,self.assess(1)]})
        self.assertEqual(m.call_count,1); self.assertEqual(r['blocking_missing_facts'],[self.q['missing_facts'][0]])
    def test_alias_context_no_canonical_ids_and_parent_links(self):
        self.assertEqual(self.aliases,short_passage_context(self.selected)[0]); self.assertEqual(len(set(self.aliases.values())),len(self.selected))
        for p in self.short:
            self.assertNotIn('evidence_id',p); self.assertIn(p['passage_id'],self.aliases)
            if p['parent_passage_id']: self.assertIn(p['parent_passage_id'],self.aliases)
    def test_real_coverage_discrepancy_blocks_original(self):
        aliases={x['evidence_id']:f'R{i:03d}' for i,x in enumerate(self.e,1)}
        judgments={'questions':[{**q,'evidence_ids':[aliases[x] for x in q['evidence_ids']]} for q in F['research_coverage']['questions']]}
        with patch.object(legal,'call_model',side_effect=[judgments,{'assessments':[self.assess(0),self.assess(1)]}]):
            covered,ready=legal.research_readiness(self.plan,self.e,dossier=self.d)
        self.assertFalse(ready); q=next(q for q in covered if q['id']=='requirements')
        self.assertEqual(q['status'],'ANSWERED_WITH_EVIDENCE'); self.assertEqual(q['draft_readiness'],'BLOCKED')
        self.assertTrue(q['gap_diagnostics']['coverage_discrepancy']); self.assertEqual(q['gap_assessments'][-1]['origin'],'APPLICABILITY_MATRIX')

    def test_alternative_selection_uses_closed_alias_schema(self):
        from editorial_scope_v50 import alternative_scope
        from test_v50_run39_passages_scope import Run39Tests
        t=Run39Tests(); t.setUp()
        alias_map,_=short_passage_context(t.selected)
        rev={v:k for k,v in alias_map.items()}
        proposal=t.proposal(['requirements:0'])
        for q in proposal['questions']:
            q['passage_ids']=[rev[p] for p in q['passage_ids']]
        covered=[{'id':'requirements','blocking_missing_facts':['Unresolved legal route'], 'gap_assessments':[{'classification':'MATERIAL'}]}]
        report={}
        with patch.object(legal,'call_model',side_effect=[proposal,t.verdict()]) as m:
            result=alternative_scope(t.plan,covered,t.e,t.dossier,call=legal.call_model,model='test',client=None,report=report)
        self.assertIsNotNone(result,report)
        self.assertEqual(m.call_count,2)
        props=m.call_args_list[0].kwargs['response_format']['json_schema']['schema']['properties']
        # Run 46 narrows the closed enum to route-compatible aliases; the
        # full alias map is retained for stable replay and diagnostics.
        from editorial_scope_v50 import passage_route_compatibility
        records={p['passage_id']:p for p in t.selected}
        expected=[a for a,pid in alias_map.items() if passage_route_compatibility(records[pid],report['primary_route'])]
        self.assertEqual(props['questions']['items']['properties']['passage_ids']['items']['enum'],expected)
        self.assertLess(len(expected),len(alias_map))
        self.assertFalse(report['publication_allowed'])
