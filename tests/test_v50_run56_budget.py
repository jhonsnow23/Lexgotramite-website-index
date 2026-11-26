"""Economical execution: no paid API calls in these tests."""
import json
from pathlib import Path
import tempfile
import unittest
from test_v50_run55_first_article import engine, ArchivedResearch, Replay, response

ROOT=Path(__file__).resolve().parents[1]

class BudgetTests(unittest.TestCase):
    def test_defaults_and_hard_config_ceiling(self):
        x=engine.Limits()
        self.assertEqual((x.usd,x.topics,x.research_rounds,x.draft_repairs,x.calls,x.output_tokens),(.25,2,2,1,6,5000))
        for kw in ({'usd':25},{'usd':.51},{'usd':float('nan')},{'usd':float('inf')},{'calls':7},{'output_tokens':12000}):
            with self.subTest(kw=kw),self.assertRaises(ValueError): engine.Limits(**kw)
        self.assertEqual(engine.Limits(usd=.5).usd,.5)

    def test_first_article_and_repair_fit_default_budget(self):
        for mode,expected in [('success',2),('repair',4)]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                result=engine.run(t,category='no_lucrativa',transport=Replay(mode),researcher_factory=ArchivedResearch)
                usage=json.loads((Path(t)/'usage.json').read_text())
                self.assertEqual(result['result'],'SIMULATED_REVIEW_PASS')
                self.assertEqual(result['api_calls'],expected)
                self.assertLess(usage['conservative_budget_debit_usd'],.25)
                self.assertEqual({c['model'] for c in usage['calls']},{'gpt-6-luna','gpt-6.1-terra'})
                self.assertTrue(all(c['max_output_tokens']==5000 for c in usage['calls']))
                self.assertFalse(result['publication_allowed']);self.assertEqual(result['articles_independently_approved'],0)
                print(f"{mode}: {expected} simulated requests, reservation ${usage['conservative_budget_debit_usd']:.6f}")

    def test_budget_checked_before_each_request_even_expensive_override(self):
        with tempfile.TemporaryDirectory() as t:
            replay=Replay(); result=engine.run(t,category='no_lucrativa',transport=replay,researcher_factory=ArchivedResearch,review_model='gpt-6.2-astra')
            self.assertEqual(result['result'],'BUDGET_EXHAUSTED')
            self.assertEqual(replay.research_calls,1);self.assertEqual(replay.review_calls,0)
            self.assertEqual(result['candidate_articles_generated'],1);self.assertFalse(result['publication_allowed'])
            self.assertEqual(result['articles_independently_approved'],0)

    def test_failed_calls_retain_reservation_and_retry_cannot_overspend(self):
        with tempfile.TemporaryDirectory() as t:
            calls=[]
            def broken(payload):
                calls.append(payload);raise TimeoutError()
            ledger=engine.Ledger(engine.Limits(usd=.030),Path(t)); model=engine.Model(ledger,broken)
            # The first Terra request reserves > $0.029 and the retry must stop.
            with self.assertRaises(engine.BudgetExhausted):
                model.call('legal_review','gpt-6.1-terra','review',{},engine.obj(ok=engine.BOOL))
            self.assertEqual(len(calls),1);self.assertEqual(len(ledger.calls),1)
            self.assertEqual(ledger.calls[0]['status'],'ERROR')
            self.assertGreater(ledger.reserved,0);self.assertLessEqual(ledger.reserved,.030)

    def test_call_limit_applies_before_transport(self):
        with tempfile.TemporaryDirectory() as t:
            sent=[]
            def ok(payload):
                sent.append(payload);return response({'ok':True},payload['model'])
            ledger=engine.Ledger(engine.Limits(calls=1),Path(t));model=engine.Model(ledger,ok)
            self.assertEqual(model.call('research',engine.RESEARCH_MODEL,'research',{},engine.obj(ok=engine.BOOL)),{'ok':True})
            with self.assertRaises(engine.BudgetExhausted):model.call('research',engine.RESEARCH_MODEL,'research',{},engine.obj(ok=engine.BOOL))
            self.assertEqual(len(sent),1)

    def test_both_workflows_use_economy_and_read_only(self):
        integration=(ROOT/'.github/workflows/lexgo-first-article-v50.yml').read_text()
        normal=(ROOT/'.github/workflows/lexgo-seo-v50.yml').read_text()
        self.assertIn('default: 0.25',integration);self.assertIn('--max-api-cost-usd 0.25',normal)
        for workflow in (integration,normal):
            self.assertIn("'gpt-6-luna'",workflow);self.assertIn("'gpt-6.1-terra'",workflow)
            self.assertIn('contents: read',workflow);self.assertNotIn('contents: write',workflow)
            self.assertNotIn('git push',workflow)

if __name__=='__main__':unittest.main()
