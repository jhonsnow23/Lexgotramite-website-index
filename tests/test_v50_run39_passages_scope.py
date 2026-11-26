import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_v50_run35_branch_applicability import legal
from editorial_scope_v50 import REVIEW_FIELDS, alternative_scope
from evidence_passages_v50 import build_catalog, resolve_passage, select_context

F=json.loads((Path(__file__).parent/'fixtures/run38_replay.json').read_text())

class Run39Tests(unittest.TestCase):
    def setUp(self):
        self.e=F['evidence']; self.plan=F['research_plan']; self.original=F['research_coverage']['questions']
        self.dossier=legal.build_dossier(self.plan,self.e)
        self.cat=build_catalog(self.e); self.selected,self.omitted=select_context(self.cat,self.e,self.dossier)
        self.ids={r['evidence_id']:f'R{i:03d}' for i,r in enumerate(self.e,1)}
    def pid(self, article):
        return next(p['passage_id'] for p in self.selected if p['article_reference']==article and not p['parent_passage_id'])
    def test_real_catalog_exact_and_stable(self):
        self.assertEqual(self.cat,build_catalog(self.e)); self.assertFalse(self.omitted)
        self.assertGreater(len(self.cat['passages']),11)
        for pid,p in self.cat['passages'].items():
            r=resolve_passage(pid,self.cat,self.e)
            self.assertEqual(r['quote'],p['verbatim_text'])
            self.assertNotIn('[...]',r['quote'])
        self.assertTrue(any(p['parent_passage_id'] for p in self.cat['passages'].values()))
        self.assertNotIn('84',[p['article_reference'] for p in self.selected])
    def test_tampered_unknown_duplicate_source(self):
        pid=self.pid('191'); altered=copy.deepcopy(self.cat); altered['passages'][pid]['verbatim_text']+='x'
        self.assertIsNone(resolve_passage(pid,altered,self.e));self.assertIsNone(resolve_passage('P_invented',self.cat,self.e))
        self.assertIsNone(resolve_passage(pid,self.cat,self.e,allowed_ids=set()))
        self.assertIsNone(resolve_passage(pid,self.cat,self.e+[self.e[0]]))
        fake={**self.e[0],'official_url':'https://example.org/fake'}
        self.assertFalse(build_catalog([fake])['passages'])
    def test_eight_actual_invalid_quotes_are_not_catalog_passages(self):
        old=[p for q in F['gap_assessment_diagnostics']['questions'] for at in q['diagnostics']['attempts'] for a in at.get('parsed_response',{}).get('assessments',[]) for p in a.get('supporting_passages',[])]
        self.assertEqual(len(old),8)
        by_id={r['evidence_id']:r for r in self.e}
        for p in old:
            self.assertNotIn(' '.join(p['quote'].split()),' '.join(by_id[p['evidence_id']]['text'].split()))
        self.assertFalse(any('Formulario EX-26: modelo de solicitud y opciones declaradas' in p['verbatim_text'] for p in self.cat['passages'].values()))
    def assess(self,i,kind='OPTIONAL_DETAIL',article='191'):
        pid=self.pid(article); ref=self.cat['passages'][pid]['evidence_id']
        return {'index':i,'classification':kind,'reason':'Synthetic classification for control-flow testing','retained_answer':'Synthetic limited explanation','limitation':'Do not infer unverified routes','evidence_ids':[self.ids[ref]],'supporting_passage_ids':[pid]}
    def test_model_selects_ids_and_python_resolves(self):
        q=self.original[1]; branch=legal.general_guidance_branch_coverage(self.e,self.dossier)
        with patch.object(legal,'call_model',return_value={'assessments':[self.assess(0,'MATERIAL'),self.assess(1)]}) as m:
            result=legal._general_guidance_missing_fact_classification(q,branch,plan=self.plan,evidence=self.e,dossier=self.dossier,model='test',client=None)
        self.assertEqual(len(result['blocking_missing_facts']),1)
        self.assertEqual(result['gap_assessments'][1]['supporting_passages'][0]['quote'],self.cat['passages'][self.pid('191')]['verbatim_text'])
        payload=json.loads(m.call_args.args[0][1]['content']); self.assertTrue(payload['official_passages'])
        self.assertTrue(all('text' not in e and 'research_relevance' not in e for e in payload['evidence']))
        self.assertIn('supporting_passage_ids',legal._gap_schema()['json_schema']['schema']['properties']['assessments']['items']['properties'])
    def proposal(self, gaps):
        route='MOD_ART191_2_AJENA_LT_1Y'
        return {'title':'Modificación por cuenta ajena tras la regularización extraordinaria de 2026: condiciones antes del año',
                'search_intent':'Continuidad por cuenta ajena antes del año','business_category':'regularizacion_2026',
                'scope':'Exclusively the documented employed-work branch','utility':'Synthetic utility','seo_rationale':'Synthetic intent match','omission_rationale':'Synthetic scope rationale',
                'excluded_gap_ids':gaps,'limitations':['No conclusion about other routes'],'individual_conditions':['Individual assessment required'],
                'questions':[{'question':'¿Qué vía se regula?','answer':'Synthetic conditional answer','route_ids':[route],'passage_ids':[self.pid('191')]},
                             {'question':'¿Qué requisitos se remiten?','answer':'Synthetic requirement answer','route_ids':[route],'passage_ids':[self.pid('74')]}]}
    def verdict(self, approved=True):
        return {**{k:approved for k in REVIEW_FIELDS if k not in ('supported_question_indices','reasons')},'supported_question_indices':[0,1],'reasons':['Synthetic independent decision']}
    def replay(self, proposal, verdict=None, draft=None, review=None):
        judgments={'questions':[{**q,'evidence_ids':[self.ids[x] for x in q['evidence_ids']]} for q in self.original]}
        assessments=[{'assessments':[self.assess(0,'MATERIAL'),self.assess(1)]},{'assessments':[self.assess(0),self.assess(1)]}]
        responses=[judgments,*assessments,proposal]
        if verdict is not None:responses.append(verdict)
        if draft is not None:responses.extend([draft,review])
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'proposal.json').write_text('{}')
            with patch.object(legal,'plan',return_value=self.plan),patch.object(legal,'retrieve_evidence',return_value=(self.e,[],{})),patch.object(legal,'focused_evidence_for_topic',side_effect=lambda p,e:(e,[])),patch.object(legal,'call_model',side_effect=responses) as m:
                rc=legal.execute(p/'proposal.json',p/'out',max_revisions=0)
            reports={x.name:json.loads(x.read_text()) for x in (p/'out').glob('*.json')}
        return rc,reports,m.call_count
    def test_real_replay_material_remains_blocked_when_alt_vetoed(self):
        rc,r,n=self.replay(self.proposal(['requirements:0']),self.verdict(False))
        self.assertEqual(rc,2,r['decision.json']);self.assertEqual(n,5)
        self.assertFalse(r['decision.json']['publication_allowed']);self.assertNotIn('article.json',r)
        self.assertEqual(r['editorial_scope_decision.json']['reason'],'INDEPENDENT_SCOPE_REJECTED')
    def test_wrong_route_and_commercial_change_rejected(self):
        for mode in ('route','category','id','missing_gap'):
            p=self.proposal(['requirements:0'])
            if mode=='route':p['questions'][1]['passage_ids']=[self.pid('86')]
            if mode=='category':p['title']='Renovación de residencia no lucrativa'
            if mode=='id':p['questions'][1]['passage_ids']=['P_INVENTED']
            if mode=='missing_gap':p['excluded_gap_ids']=[]
            rc,r,n=self.replay(p)
            self.assertEqual(rc,2); self.assertEqual(n,4);self.assertEqual(r['editorial_scope_decision.json']['status'],'REJECTED')
    def test_real_replay_draft_and_final_veto(self):
        p=self.proposal(['requirements:0']); text='El artículo 191 contempla modificaciones de autorizaciones de residencia según el supuesto aplicable.'
        draft={'title':p['title'],'meta_description':text,'introduction':text,'sections':[{'heading':h,'paragraphs':[text]} for h in ('Alcance','Condiciones','Procedimiento')],'faqs':[],'claims':[{'claim':text,'evidence_ids':[self.e[0]['evidence_id']]}],'unresolved_questions':[]}
        for outcome,code in [('SUPPORTED',0),('BLOCKED',3)]:
            review={'assessment':[{'claim_index':0,'status':'SUPPORTED'}],'gaps':[],'scope_limitations_status':outcome}
            rc,r,n=self.replay(p,self.verdict(),draft,review)
            self.assertEqual(rc,code,r['decision.json']);self.assertEqual(n,7)
            self.assertFalse(r['research_coverage.json']['ready']);self.assertFalse(r['decision.json']['publication_allowed'])
            self.assertTrue(r['decision.json']['adaptive_editorial_scope']);self.assertIn('article.json',r)
    def test_title_change_rejected_even_if_reviewer_approves(self):
        p=self.proposal(['requirements:0']); text='El artículo 191 contempla modificaciones de autorizaciones de residencia según el supuesto aplicable.'
        draft={'title':self.plan['topic'],'meta_description':text,'introduction':text,'sections':[{'heading':h,'paragraphs':[text]} for h in ('Alcance','Condiciones','Procedimiento')],'faqs':[],'claims':[{'claim':text,'evidence_ids':[self.e[0]['evidence_id']]}],'unresolved_questions':[]}
        rc,r,_=self.replay(p,self.verdict(),draft,{'assessment':[{'claim_index':0,'status':'SUPPORTED'}],'gaps':[],'scope_limitations_status':'SUPPORTED'})
        self.assertEqual(rc,3);self.assertIn('Draft changed the independently authorized alternative title',r['decision.json']['errors'])
