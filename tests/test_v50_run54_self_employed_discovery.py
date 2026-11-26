"""Run 53 replay: observed index candidates, not legal certification."""
import json, unittest
from pathlib import Path
from unittest.mock import Mock
from test_v50_run51_arraigo_research import index
from test_v50_run35_branch_applicability import legal
import legal_relevance_v50 as relevance
from editorial_scope_v50 import alternative_scope
F=json.loads((Path(__file__).parent/'fixtures/run53_replay.json').read_text())
TOPIC=F['research_plan']['topic']
class Run54Tests(unittest.TestCase):
    def test_real_missing_provisions_prioritized(self):
        old={r['article'] for r in F['discovery_diagnostics']['provision_attempts']}
        self.assertTrue({'86','87'}.isdisjoint(old))
        found,report=relevance.discover('renewal',TOPIC,index_fetch=lambda _: (index(),'synthetic'))
        ids={r['article']:r['block_id'] for r in found}
        for n in ('86','87','84','66'): self.assertEqual(ids[n],f'observed-block-{n}')
        self.assertEqual(len(found),48)
        self.assertEqual(report[0]['uninspected_index_articles'],217)
    def test_ranked_index_preserves_priorities(self):
        root=index()
        for child in root:
            if child.get('id')=='observed-block-80': child.set('titulo','Artículo 80. Renovación de residencia y trabajo por cuenta ajena')
        found,_=relevance.discover('renewal',TOPIC,index_fetch=lambda _: (root,'synthetic'))
        self.assertTrue({'86','87'}<={r['article'] for r in found})
    def test_no_invented_index_entry_or_automatic_relevance(self):
        found,_=relevance.discover('renewal',TOPIC,index_fetch=lambda _: (index(omit=(86,)),'synthetic'))
        self.assertNotIn('86',{r['article'] for r in found})
        self.assertFalse(relevance.provision_relevance('renewal',TOPIC,'Artículo 86. Normas de tráfico.',F['research_plan']['research_questions'])['relevant'])
    def test_other_modalities_not_inherited(self):
        for topic in ('Renovación de residencia y trabajo por cuenta ajena','Renovación de residencia no lucrativa','Renovación de residencia de larga duración','Renovación de arraigo con trabajo por cuenta propia'):
            self.assertNotIn('87',relevance._topic_priority_articles('renewal',topic))
        self.assertEqual(relevance._topic_priority_articles('arraigo','Prórroga o modificación de arraigo sociolaboral')[0],'132')
    def test_actual_negative_verdict_still_blocks(self):
        p=F['research_plan'];e=F['evidence'];d=legal.build_dossier(p,e);c=F['research_coverage']['questions'];a=F['attempts'][0];report={}
        call=Mock(side_effect=[a['proposal'],a['independent_scope_review']])
        self.assertIsNone(alternative_scope(p,c,e,d,call=call,model='gpt-4.1-mini',client=None,report=report,max_proposals=1))
        self.assertEqual(report['reason'],'INDEPENDENT_SCOPE_REJECTED')
        self.assertFalse(report['publication_allowed'])
    def test_all_six_seed_categories_have_entry_points(self):
        from temporary_residence_policy_v50 import SEEDS
        expected={'regularizacion_2026':('191',), 'arraigo':('132','191'),
                  'cuenta_ajena':('80','81'), 'cuenta_propia':('86','87'),
                  'no_lucrativa':('64',), 'menores_no_nacidos':('160',)}
        for category, core in expected.items():
            with self.subTest(category=category):
                topic=SEEDS[category]['proposed_title'];group='arraigo' if category in ('arraigo','regularizacion_2026') else 'renewal'
                found, reports=relevance.discover(group,topic,index_fetch=lambda _: (index(),'synthetic'))
                self.assertTrue(set(core)<={r['article'] for r in found})
                self.assertTrue(set(core)<=set(reports[0]['priority_articles_selected']))
                self.assertEqual(len(found),48)
    def test_missing_priority_is_disclosed_and_never_guessed(self):
        found,reports=relevance.discover('renewal',TOPIC,index_fetch=lambda _: (index(omit=(86,)),'synthetic'))
        self.assertIn('86',reports[0]['priority_articles_missing_from_index'])
        self.assertNotIn('86',reports[0]['priority_articles_selected'])
        self.assertNotIn('86',{x['article'] for x in found})
    def test_mixed_ordinary_modalities_not_prioritized(self):
        self.assertEqual(relevance._topic_priority_articles('renewal','Renovación cuenta propia y cuenta ajena'),())
        self.assertEqual(relevance._topic_priority_articles('renewal','Renovación residencia no lucrativa y cuenta propia'),())
