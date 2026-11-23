import importlib.util
import json
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import seo_v50 as mod

class TestV50(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((ROOT/'fixtures/gsc_report.json').read_text(encoding='utf8'))
        cls.catalog=json.loads((ROOT/'config/seo_v42_services.json').read_text(encoding='utf8'))

    def rows(self,history=None,**kwargs):
        with tempfile.TemporaryDirectory() as t:
            return mod.choose(self.report,self.catalog,t,history or [],date(2026,11,23),**kwargs)

    def test_old_attempt_never_triggers_60_day_cooldown(self):
        ev={'cluster_id':'residency_options','selected_on':'2026-11-15','status':'DRAFT_FAILED'}
        rows,chosen,_=self.rows([ev])
        match=next(x for x in rows if x['cluster_id']=='residency_options')
        self.assertNotEqual(match['recommended_action'],'MONITOR')

    def test_publication_has_60_day_cooldown(self):
        ev={'cluster_id':'residency_options','selected_on':'2026-11-15','status':'PUBLISHED'}
        rows,_,_=self.rows([ev]);match=next(x for x in rows if x['cluster_id']=='residency_options')
        self.assertEqual(match['recommended_action'],'MONITOR')

    def test_legacy_ambiguous_history_short_backoff(self):
        ev={'cluster_id':'residency_options','selected_on':'2026-11-23'}
        rows,_,_=self.rows([ev]);match=next(x for x in rows if x['cluster_id']=='residency_options')
        self.assertEqual(match['recommended_action'],'MONITOR')
        rows2,_,_=self.rows([ev],retry_failed=True)
        self.assertNotEqual(next(x for x in rows2 if x['cluster_id']=='residency_options')['recommended_action'],'MONITOR')

    def test_manual_retry_does_not_override_published(self):
        ev={'cluster_id':'residency_options','selected_on':'2026-11-23','status':'PUBLISHED'}
        rows,_,_=self.rows([ev],retry_failed=True)
        self.assertEqual(next(x for x in rows if x['cluster_id']=='residency_options')['recommended_action'],'MONITOR')

    def test_search_console_measured_demand(self):
        rows,selected,proposal=self.rows()
        self.assertEqual(len(rows),8)
        self.assertIn(selected['cluster_id'], {x['cluster_id'] for x in rows})
        self.assertEqual(proposal['proposals'][0]['origin_cluster_id'],selected['cluster_id'])

    def test_no_unverified_keyword_volume(self):
        rows,_,_=self.rows()
        self.assertTrue(all('impressions_28d' in x and 'score_breakdown' in x for x in rows))

    def test_unsupported_registry_does_not_generate(self):
        rows,_,_=self.rows()
        x=next(x for x in rows if x['cluster_id']=='regularization_processing')
        self.assertEqual(x['recommended_action'],'MONITOR')
        self.assertFalse(x['research_registry_available'])

    def test_no_key_still_local_mode(self):
        self.assertEqual(mod.load_history(token='',repository='')[0],[])

    def test_api_outage_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError,'History recovery failed'):
            mod.load_history(token='fake',repository='o/r',fetch=lambda url: (_ for _ in ()).throw(TimeoutError()))

    def test_finalization_records_failure_not_publishing(self):
        with tempfile.TemporaryDirectory() as t:
            out=Path(t)
            mod.save(out/'selection.json',{'selected':{'cluster_id':'residency_options','existing_pages':[]}})
            mod.save(out/'history.json',{'events':[]})
            decision=out/'article'/'decision.json'
            mod.save(decision,{'result':'BLOCKED_VALIDATION'})
            from types import SimpleNamespace
            self.assertEqual(mod.finalize(SimpleNamespace(output=str(out),decision=str(decision))),0)
            hist=json.loads((out/'history.json').read_text())['events'][-1]
            self.assertEqual(hist['status'],'BLOCKED_VALIDATION')
            self.assertFalse(hist['published'])

    def test_sanitizes_token_on_cross_host_redirect(self):
        req=mod.urllib.request.Request('https://api.github.com/foo',headers={'Authorization':'Bearer secret'})
        r=mod.ArtifactRedirect().redirect_request(req,None,302,'Found',{},'https://objects.githubusercontent.com/blob')
        self.assertNotIn('Authorization',r.headers)

if __name__=='__main__':unittest.main()
