"""Replay actual Run 62 research and evidence; all new reviews are simulated."""
import copy,json,tempfile,unittest
from pathlib import Path
from test_v50_run55_first_article import engine, ArchivedResearch, response, verdict

F=json.loads((Path(__file__).parent/'fixtures/run62_live_replay.json').read_text())
ROOT=Path(__file__).resolve().parents[1]

class Run62Research(ArchivedResearch):
    def article(self, document, article):
        self.ledger.document(f'{document}:{article}')
        return copy.deepcopy([r for r in F['evidence'] if r['source_id']==document and r.get('article')==str(article)])
    def guidance(self, category, topic):
        return copy.deepcopy([r for r in F['evidence'] if r['authority']=='migraciones'])

class NarrowAnswer(unittest.TestCase):
    def replay(self, mode='success', article_type='specific_question'):
        calls=[]
        def transport(payload):
            data=json.loads(payload['input']); stage=payload['text']['format']['name']; calls.append(stage)
            if stage=='research':
                raw=copy.deepcopy(F['research_round_01'])
                self.assertEqual(next(p['passage_id'] for p in data['official_passages'] if p['article']=='64'),'P001')
                if mode=='empty':raw['claims']=[]
                if mode=='invented':raw['claims'][0]['passage_ids']=['P999']
                if mode=='uncited_gap':raw['gaps']=[{'question':'Material gap','classification':'MATERIAL_LEGAL_GAP','reason':'Unresolved','reader_limitation':'Not resolved','passage_ids':[]}]
                return response(raw,payload['model'])
            self.assertEqual(len(data['claims']),1)
            self.assertIn('dos años',data['rendered_markdown'])
            self.assertIn('larga duración-UE',data['rendered_markdown'])
            self.assertIn('no a la tarjeta física',data['rendered_markdown'])
            review=verdict(data,approved=mode!='veto')
            if mode=='veto':
                review['scope_complete']=False
                review['defects']=[{'location':'Introducción','problem':'Simulated material omission','correction':'Resolve the omission before approval','additional_articles':[]}]
            return response(review,payload['model'])
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            result=engine.run(root,proposal=F['proposal'],bootstrap=False,article_type=article_type,transport=transport,researcher_factory=Run62Research,website_root=root/'empty-website',limits=engine.Limits(topics=1,research_rounds=1,draft_repairs=0))
            files={str(p.relative_to(root)):p.read_text() for p in root.rglob('*') if p.is_file()}
        self.assertFalse(result['publication_allowed']);self.assertEqual(result['articles_independently_approved'],0)
        self.assertNotIn('topic_01_no_lucrativa/article.md',files)
        return result,files,calls

    def test_exact_live_response_now_reaches_review(self):
        self.assertEqual(F['decision']['reason'],'Insufficient substantive supported paragraphs')
        self.assertEqual(len(F['research_round_01']['claims']),1)
        result,files,calls=self.replay()
        self.assertEqual(result['result'],'SIMULATED_REVIEW_PASS',result)
        self.assertEqual(calls,['research','legal_review'])
        self.assertEqual(result['candidate_articles_generated'],1)
        self.assertIn('NARROW_ANSWER_CANDIDATE',files['topic_01_no_lucrativa/state.json'])
        self.assertIn('NO APROBADO',files[result['simulated_article']])

    def test_one_claim_does_not_override_legal_veto(self):
        result,files,calls=self.replay('veto')
        self.assertEqual(result['result'],'BLOCKED_LEGAL_VALIDATION')
        self.assertEqual(calls,['research','legal_review']);self.assertNotIn('simulated_article',result)

    def test_empty_claims_still_block(self):
        result,_,calls=self.replay('empty')
        self.assertEqual(result['result'],'BLOCKED_INSUFFICIENT_EVIDENCE');self.assertEqual(calls,['research'])

    def test_broader_guide_retains_previous_gate(self):
        result,_,calls=self.replay(article_type='procedure')
        self.assertEqual(result['result'],'BLOCKED_INSUFFICIENT_EVIDENCE');self.assertEqual(calls,['research'])

    def test_uncited_material_gap_still_blocks(self):
        result,_,calls=self.replay('uncited_gap')
        self.assertEqual(result['result'],'BLOCKED_INSUFFICIENT_EVIDENCE');self.assertEqual(calls,['research'])

    def test_invalid_reference_never_reaches_review(self):
        result,_,calls=self.replay('invented')
        self.assertNotIn(result['result'],('SIMULATED_REVIEW_PASS','REVIEW_READY'));self.assertTrue(calls);self.assertTrue(all(c=='research' for c in calls));self.assertLessEqual(len(calls),engine.Limits.calls)

if __name__=='__main__':unittest.main()
