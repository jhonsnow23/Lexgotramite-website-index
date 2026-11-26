"""Run 50 replay: discovery and evidence-reference contracts, not legal approval."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from test_v50_run35_branch_applicability import legal
import legal_relevance_v50 as relevance
from editorial_scope_v50 import alternative_scope
from unittest.mock import Mock

F=json.loads((Path(__file__).parent/'fixtures/run50_replay.json').read_text())
TOPIC=F['research_plan']['topic']

def index(informative=False, omit=()):
    root=ET.Element('indice')
    for n in range(1,266):
        if n in omit:continue
        label=f'Artículo {n}'
        if informative and n in (125,130): label+=' Requisitos y procedimiento de arraigo sociolaboral'
        ET.SubElement(root,'bloque',id=f'observed-block-{n}',titulo=label)
    return root

class Run51Tests(unittest.TestCase):
    def test_actual_probe_missed_core_articles_now_prioritized(self):
        old={x['article'] for x in F['discovery_diagnostics']['provision_attempts']}
        self.assertNotIn('132',old);self.assertNotIn('191',old)
        found,reports=relevance.discover('arraigo',TOPIC,index_fetch=lambda _: (index(),'synthetic-index'))
        actual={x['article']:x['block_id'] for x in found}
        for num in ('132','191','127','131','86'):
            self.assertEqual(actual[num],f'observed-block-{num}')
        self.assertEqual(len(found),48);self.assertEqual(reports[0]['uninspected_index_articles'],217)
    def test_informative_index_does_not_displace_core_articles(self):
        found,_=relevance.discover('arraigo',TOPIC,index_fetch=lambda _: (index(True),'synthetic'))
        self.assertTrue({'132','191'}<={x['article'] for x in found});self.assertLessEqual(len(found),12)
    def test_missing_article_never_invented_and_irrelevant_text_rejected(self):
        found,_=relevance.discover('arraigo',TOPIC,index_fetch=lambda _: (index(omit=(132,)),'synthetic'))
        self.assertNotIn('132',{x['article'] for x in found})
        self.assertFalse(relevance.provision_relevance('arraigo',TOPIC,'Artículo 132. Normas de tráfico.',F['research_plan']['research_questions'])['relevant'])
    def test_distinguish_specific_modality_and_comparison(self):
        plan=legal.plan(F['selected_proposal'])
        self.assertIsNone(plan['commercial_classification']['procedure_type'])
        self.assertTrue(all('arraigo sociolaboral' in q['question'] for q in plan['research_questions']))
        self.assertFalse(plan['publication_allowed'])
        self.assertEqual(relevance._topic_priority_articles('arraigo','Cómo continuar la residencia tras la regularización extraordinaria de 2026'),('191',))
    def test_replay_full_references_only_in_structured_field_and_closed_schema(self):
        e=F['evidence'];plan=legal.plan(F['selected_proposal']);d=legal.build_dossier(plan,e)
        # Original raw structured response was not logged. Simulate the observed
        # ID confusion using the actual evidence IDs and stored partial judgments.
        q=F['research_coverage']['questions']; judgments={'questions':[{**row,'evidence_ids':[e[-2]['evidence_id'],'R999']} for row in q]}
        with patch.object(legal,'call_model',return_value=judgments) as m:
            covered,ready=legal.research_readiness(plan,e,dossier=d)
        self.assertFalse(ready); self.assertTrue(all(x['status']=='PARTIALLY_ANSWERED' for x in covered))
        self.assertTrue(all(x['evidence_ids']==[e[-2]['evidence_id']] for x in covered))
        self.assertTrue(all(x['research_reference_diagnostics']['rejected']==['R999'] for x in covered))
        props=m.call_args.kwargs['response_format']['json_schema']['schema']['properties']['questions']['items']['properties']
        self.assertEqual(props['evidence_ids']['items']['enum'],[f'R{i:03d}' for i in range(1,len(e)+1)])
        payload=json.loads(m.call_args.args[0][1]['content']); self.assertEqual(payload['legal_applicability_dossier']['applicability_evidence'][-2]['evidence_id'],f'R{len(e)-1:03d}')
        self.assertNotIn('DA20.10 and DA21.10 are separate origins',m.call_args.args[0][0]['content'])
        self.assertIn('Article 132',m.call_args.args[0][0]['content'])
    def test_actual_empty_references_are_not_inferred_from_reason(self):
        plan=legal.plan(F['selected_proposal']); e=F['evidence'];d=legal.build_dossier(plan,e)
        with patch.object(legal,'call_model',return_value={'questions':F['research_coverage']['questions']}):
            covered,ready=legal.research_readiness(plan,e,dossier=d)
        self.assertFalse(ready);self.assertTrue(all(not x['evidence_ids'] for x in covered))
        report={};call=Mock();self.assertIsNone(alternative_scope(plan,covered,e,d,call=call,model='test',client=None,report=report))
        self.assertEqual(report['status'],'NO_RECORDED_MATERIAL_GAP');call.assert_not_called(); self.assertFalse(report['publication_allowed'])
