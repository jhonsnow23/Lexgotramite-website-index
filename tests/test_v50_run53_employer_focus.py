import copy,json,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from test_v50_run35_branch_applicability import legal
from editorial_scope_v50 import alternative_scope
from temporary_residence_policy_v50 import employer_change_focus
F=json.loads((Path(__file__).parent/'fixtures/run52_replay.json').read_text())
class Run53Tests(unittest.TestCase):
    def test_plan_retains_material_search_intent(self):
        p=legal.plan(F['selected_proposal'])
        self.assertEqual(p['material_search_focus'],'EMPLOYER_CHANGE_RENEWAL')
        self.assertEqual([q['id'] for q in p['research_questions']],['scope','requirements','steps'])
        for q in p['research_questions']:
            self.assertIn('empleador',q['question']); self.assertIn('empleador',q['query'])
        self.assertIn('80.2.b',p['research_questions'][0]['question'])
        self.assertFalse(p['publication_allowed'])
    def test_focus_is_not_applied_to_other_categories(self):
        self.assertFalse(employer_change_focus('arraigo','cambio de empleador'))
        self.assertFalse(employer_change_focus('cuenta_ajena','Renovación de residencia y trabajo por cuenta ajena'))
        self.assertTrue(employer_change_focus('cuenta_ajena','Renovación por cuenta ajena con nuevo empleador'))
    def test_research_prompt_checks_conditions_without_approving(self):
        p=legal.plan(F['selected_proposal']);e=F['evidence'];d=legal.build_dossier(p,e)
        qs=F['research_coverage']['questions']
        with patch.object(legal,'call_model',return_value={'questions':qs}) as m:
            covered,ready=legal.research_readiness(p,e,dossier=d)
        self.assertFalse(ready)
        self.assertIn('employer-change qualifier is essential',m.call_args_list[0].args[0][0]['content'])
        self.assertTrue(all(q['status']=='PARTIALLY_ANSWERED' for q in covered))
    def test_real_generic_alternatives_cannot_discard_employer_change(self):
        p=F['research_plan'];e=F['evidence'];d=legal.build_dossier(p,e);c=copy.deepcopy(F['research_coverage']['questions']); report={}
        m=Mock(side_effect=[x['proposal'] for x in F['attempts']])
        result=alternative_scope(p,c,e,d,call=m,model='gpt-4.1-mini',client=None,report=report)
        self.assertIsNone(result);self.assertEqual(m.call_count,3)
        self.assertEqual(report['attempts'][0]['reason'],'MATERIAL_SEARCH_FOCUS_LOST')
        self.assertFalse(report['publication_allowed']);self.assertEqual(c,F['research_coverage']['questions'])
    def test_specific_title_still_requires_independent_review(self):
        p=F['research_plan'];e=F['evidence'];d=legal.build_dossier(p,e);c=F['research_coverage']['questions']; report={}
        a=F['attempts'][0]; proposal={**a['proposal'],'title':'Renovación por cuenta ajena con nuevo empleador: requisitos del nuevo contrato'}
        m=Mock(side_effect=[proposal,a['independent_scope_review']]);result=alternative_scope(p,c,e,d,call=m,model='gpt-4.1-mini',client=None,report=report,max_proposals=1)
        self.assertIsNone(result);self.assertEqual(report['reason'],'INDEPENDENT_SCOPE_REJECTED');self.assertEqual(m.call_count,2)
        self.assertIn('Do not remove that topic',m.call_args.args[0][0]['content']);self.assertFalse(report['publication_allowed'])
