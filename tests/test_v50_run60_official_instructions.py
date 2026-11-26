"""Run59 actual rejected candidates + deterministic new source discovery tests."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_v50_run55_first_article import engine, response, ArchivedResearch
import official_sources_v50 as src
import legal_content_v50 as legal
import legal_applicability_v50 as app
F=json.loads((Path(__file__).parent/'fixtures/run59_live_replay.json').read_text())
TOPIC=F['research_plan.json']['topic']

class Archive(ArchivedResearch):
    def article(self, document, article):
        self.ledger.document(f'{document}:{article}')
        return copy.deepcopy([r for r in F['evidence.json'] if r['source_id']==document and r.get('article')==str(article)])
    def guidance(self, category, topic):
        return copy.deepcopy([r for r in F['evidence.json'] if r['authority']=='migraciones'])

class Run60(unittest.TestCase):
    def test_source_discovery_exact_and_scoped(self):
        rows=src.candidates(TOPIC,'arraigo')
        self.assertEqual(rows,[src.SOURCES['arraigo_temporal'][1],src.SEM1,src.SEM4,src.CAT_INTEGRATION])
        self.assertNotIn(src.CAT_INTEGRATION,src.candidates('Requisitos arraigo social Madrid','arraigo'))
        self.assertNotIn(src.SEM1,src.candidates('Prórroga del arraigo social Cataluña','arraigo'))
        self.assertNotIn(src.CAT_INTEGRATION,src.candidates('Renovación residencia no lucrativa Cataluña','renewal'))
        self.assertTrue(all(src.allowed(r[2]) for r in rows))
        self.assertFalse(src.allowed('https://tramits.gencat.cat.evil.example/'))
    def test_instruction_extractor_preserves_both_distant_passages(self):
        a='A efectos del cómputo de permanencia continuada, las ausencias de España no podrán superar los 90 días naturales.'
        b='Requisitos específicos de arraigo social. El criterio administrativo indica un total del 200% del IPREM.'
        # Synthetic extraction input, not a purported copy of the official PDF.
        text='prefacio '*500+a+' relleno '*3000+b+' cierre '*300
        excerpt=src.focused_instruction_excerpt(text,'SEM1')
        self.assertIn(a,excerpt);self.assertIn(b,excerpt);self.assertIn('\n[...]\n',excerpt)
        self.assertLess(len(excerpt),8000)
        with self.assertRaises(ValueError):src.focused_instruction_excerpt('No relevant text','SEM1')
    def test_pdf_dispatch_does_not_use_regularisation_faq(self):
        text='Prefacio '*40+'ausencias de España durante el período de dos años. '*8+'200% del IPREM. '*8
        with patch.object(src,'extract_pdf_text',return_value=text),patch.object(src,'excerpt_for_procedure_guidance',side_effect=AssertionError('wrong extractor')):
            record=src.retrieve_one(*src.SEM1,fetch=lambda _:b'%PDF fixture')
        self.assertIn('200% del IPREM',record['text']);self.assertIn('ausencias de España',record['text'])
        self.assertEqual(record['legal_status'],'PROCEDURAL_GUIDANCE_UNVERIFIED')
    def test_regional_guidance_requires_matching_scope_and_boe(self):
        rec=src.retrieve_one(*src.CAT_INTEGRATION,fetch=lambda _: '<p>Este informe tiene como finalidad acreditar el esfuerzo de integración.</p>'+'<p>Texto simulado de una guía regional.</p>'*8)
        plan=legal.plan({'proposals':[{'proposed_title':TOPIC}]})
        national=legal.plan({'proposals':[{'proposed_title':'Requisitos arraigo social Madrid'}]})
        self.assertEqual(app.build_dossier(plan,[rec])['applicability_evidence'][0]['applicability'],'PROCEDURAL_GUIDANCE')
        self.assertEqual(app.build_dossier(national,[rec])['applicability_evidence'][0]['applicability'],'UNRELATED')
        cat,dossier,aliases,_=engine.source_context([rec],plan)
        claim={'claims':[{'text':'Una afirmación de prueba','section':'Prueba','conditions':'','exceptions':'','passage_ids':['P001']}],'gaps':[]}
        with self.assertRaisesRegex(engine.IntegrityError,'BOE basis'):engine.validate_research(claim,aliases,cat,[rec],dossier)
    def test_initial_plan_not_continuity(self):
        plan=legal.plan({'proposals':[{'proposed_title':TOPIC}]})
        self.assertEqual(plan['material_search_focus'],'INITIAL_SOCIAL_ARRAIGO')
        self.assertIn('acceso inicial',plan['research_questions'][0]['question'])
        self.assertIn('SEM 1/2025',plan['research_questions'][1]['query'])
        self.assertIn('Generalitat',plan['research_questions'][2]['query'])
    def test_replay_preserves_review_on_integrity_retry_and_actual_veto(self):
        replies=[F['research_round_01.json'],F['candidates/01/legal_review.json']['verdict'],F['research_round_02.json'],F['research_round_03.json'],F['candidates/02/legal_review.json']['verdict']]
        stages=[]
        def transport(payload):
            i=len(stages);stage=payload['text']['format']['name'];data=json.loads(payload['input']);stages.append(stage)
            if i==0:
                self.assertIn('SEM 1/2025',payload['instructions']);self.assertTrue(all('source_title' in x for x in data['official_passages']))
            if i==3:
                feedback=data['historical_review_feedback'];self.assertIn('BOE basis',feedback['integrity_error']);self.assertEqual(len(feedback['unresolved_prior_defects']),5)
                self.assertIn('defects',feedback);self.assertIn('prior_article',feedback)
            result=response(copy.deepcopy(replies[i]),payload['model']);result['usage']=F['api_usage.json']['calls'][i]['usage'];return result
        with tempfile.TemporaryDirectory() as t:
            result=engine.run(t,proposal=F['selected_proposal.json'],bootstrap=False,article_type='information',transport=transport,researcher_factory=Archive)
            self.assertEqual(stages,['research','legal_review','research','research','legal_review'],result)
            self.assertEqual(result['result'],'BLOCKED_LEGAL_VALIDATION');self.assertEqual(result['candidate_articles_generated'],2)
            self.assertEqual(result['articles_independently_approved'],0);self.assertFalse(result['publication_allowed'])
            self.assertFalse(list(Path(t).rglob('article.md')))
            self.assertLess(result['conservative_budget_debit_usd'],.25)
            self.assertIn(engine.LO+':1',[x['key'] for x in json.loads((Path(t)/'usage.json').read_text())['documents']])

if __name__=='__main__':unittest.main()
