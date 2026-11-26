"""Replay real Run58 source/model outputs; no paid API requests."""
import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from test_v50_run55_first_article import engine, response, verdict, ArchivedResearch
import seo_v50 as seo
F=json.loads((Path(__file__).parent/'fixtures/run58_live_replay.json').read_text())

class LiveArchive(ArchivedResearch):
    def article(self, document, article):
        self.ledger.document(f'{document}:{article}')
        return copy.deepcopy([r for r in F['evidence.json'] if r['source_id']==document and r.get('article')==str(article)])
    def guidance(self, category, topic):
        return copy.deepcopy([r for r in F['evidence.json'] if r['authority']=='migraciones'])

class Run59(unittest.TestCase):
    def test_exact_recorded_usage_and_reservations(self):
        rows=F['api_usage.json']['calls']
        with tempfile.TemporaryDirectory() as t:
            l=engine.Ledger(engine.Limits(),Path(t))
            for old in rows:
                # Reconstruct the measured byte-length bound, not the original prompt.
                payload={'max_output_tokens':old['max_output_tokens'],'input':''}
                payload['input']='x'*(old['input_token_upper_estimate']-4096-len(engine.encoded(payload).encode()))
                row=l.reserve(old['model'],payload)
                self.assertAlmostEqual(row['reserved_usd'],old['reserved_usd'])
                row.update(status='COMPLETED',response_model=old['response_model'],usage=old['usage'])
                l.settle(row)
            self.assertAlmostEqual(l.reserved,2*F['api_usage.json']['estimated_usd'],places=6)
            # Even a 140k-byte upper-bound second review fits now; previously
            # $0.151182 + $0.165 would have exceeded the same $0.25 cap.
            row=l.reserve(engine.REVIEW_MODEL,{'max_output_tokens':5000,'input':'x'*140000})
            self.assertLess(l.reserved,.25);self.assertEqual(len(l.calls),5)
            self.assertGreater(.151182+row['reserved_usd'],.25)
    def test_unknown_or_failed_usage_keeps_reservation(self):
        with tempfile.TemporaryDirectory() as t:
            for usage, status, model in [({},'COMPLETED',engine.REVIEW_MODEL),({'input_tokens':100,'output_tokens':100},'ERROR',engine.REVIEW_MODEL),({'input_tokens':100,'output_tokens':100},'COMPLETED','different-model'),({'input_tokens':100,'output_tokens':100,'total_tokens':1},'COMPLETED',engine.REVIEW_MODEL),({'input_tokens':100,'output_tokens':9000},'COMPLETED',engine.REVIEW_MODEL)]:
                l=engine.Ledger(engine.Limits(),Path(t));r=l.reserve(engine.REVIEW_MODEL,{'max_output_tokens':5000,'input':'test'})
                original=l.reserved;r.update(status=status,response_model=model,usage=usage);l.settle(r)
                self.assertEqual(l.reserved,original);self.assertNotIn('settled_debit_usd',r)
    def test_reservation_reconciled_once(self):
        with tempfile.TemporaryDirectory() as t:
            l=engine.Ledger(engine.Limits(),Path(t));r=l.reserve(engine.REVIEW_MODEL,{'max_output_tokens':5000,'input':'test'})
            r.update(status='COMPLETED',response_model=engine.REVIEW_MODEL,usage={'input_tokens':100,'output_tokens':100,'total_tokens':200});l.settle(r);cost=l.reserved;l.settle(r)
            self.assertAlmostEqual(cost,.0012);self.assertEqual(cost,l.reserved)
    def test_replay_actual_rejection_reaches_second_review(self):
        stages=[];replies=[F['research_round_01.json'],F['research_round_02.json'],F['candidates/01/legal_review.json']['verdict'],F['research_round_03.json']]
        def transport(payload):
            stage=payload['text']['format']['name'];data=json.loads(payload['input']);i=len(stages);stages.append(stage)
            if i<4:
                raw=copy.deepcopy(replies[i]); result=response(raw,payload['model']); result['usage']=F['api_usage.json']['calls'][i]['usage'];return result
            # No real second review was made. A deliberately negative simulated
            # verdict proves the second candidate remains unapproved.
            raw=verdict(data,approved=False,resolve=False)
            raw['blocking_gap_checks']=[{'gap_id':g['gap_id'],'resolution':'STILL_BLOCKING','reason':'Simulated negative review','passage_ids':[]} for g in data['blocking_gaps']]
            return response(raw,payload['model'])
        with tempfile.TemporaryDirectory() as t,patch.object(engine,'priority_articles',return_value=engine.PROFILES['arraigo'][1]):
            result=engine.run(t,proposal=F['selected_proposal.json'],bootstrap=False,article_type='information',transport=transport,researcher_factory=LiveArchive)
            self.assertEqual(stages,['research','research','legal_review','research','legal_review'],result)
            self.assertEqual(result['result'],'BLOCKED_LEGAL_VALIDATION');self.assertEqual(result['candidate_articles_generated'],2)
            self.assertEqual(result['articles_independently_approved'],0);self.assertFalse(result['publication_allowed']);self.assertLess(result['conservative_budget_debit_usd'],.25)
    def test_specific_arraigo_social_priorities(self):
        self.assertEqual(engine.priority_articles('arraigo',F['selection.json']['selected']['proposed_title']),(127,126,84,124))
        self.assertEqual(engine.priority_articles('arraigo','Prórroga del arraigo sociolaboral'),engine.PROFILES['arraigo'][1])
        self.assertEqual(engine.priority_articles('arraigo','Prórroga del arraigo social'),engine.PROFILES['arraigo'][1])
        self.assertEqual(engine.priority_articles('no_lucrativa','Renovación de residencia no lucrativa'),(64,62))
        with tempfile.TemporaryDirectory() as t:
            def transport(payload):
                data=json.loads(payload['input']);arts={p['article'] for p in data['official_passages']}
                self.assertTrue({'127','126','84','124'}<=arts);self.assertNotIn('132',arts)
                self.assertIn('IPREM',payload['instructions']);return response({'claims':[],'gaps':[],'additional_articles':[]},payload['model'])
            result=engine.run(t,proposal=F['selected_proposal.json'],bootstrap=False,article_type='information',transport=transport,researcher_factory=LiveArchive)
            self.assertEqual(result['result'],'BLOCKED_INSUFFICIENT_EVIDENCE');self.assertEqual(result['api_calls'],1)
    def test_finalize_budget_status_and_backoff(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);engine.save(p/'selection.json',F['selection.json']);engine.save(p/'history.json',{'events':[]});engine.save(p/'decision.json',F['decision.json'])
            seo.finalize(SimpleNamespace(output=t,decision=str(p/'decision.json')))
            self.assertEqual(json.loads((p/'run_summary.json').read_text())['result'],'BUDGET_EXHAUSTED')
            history=json.loads((p/'history.json').read_text());self.assertIsNotNone(seo.topic_blocker(F['selection.json']['selected'],history,seo.date.today()));self.assertFalse(history['events'][-1]['publication_allowed'])
if __name__=='__main__':unittest.main()
