import importlib.util
import json
from datetime import date
from pathlib import Path
import tempfile
import unittest

P=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('seo_v42',P/'scripts/seo_v42.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TestDemandSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((P/'fixtures/gsc_report.json').read_text())
        cls.catalog=json.loads((P/'config/seo_v42_services.json').read_text())
    def test_only_verified_source(self):
        rep=json.loads(json.dumps(self.report));rep['metadata']['verified_google_data']=False
        with self.assertRaises(ValueError):mod.validate_report(rep)
    def test_eight_real_clusters_no_invention(self):
        with tempfile.TemporaryDirectory() as temp:
            rows=mod.rank(self.report,self.catalog,temp,[],date(2026,11,23))
        self.assertEqual(len(rows),8)
        self.assertEqual(len(set(x['cluster_id'] for x in rows)),8)
        self.assertTrue(all(x['demand_source'].startswith('Google') for x in rows))
    def test_cooldown_prevents_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            history=[{'selected_on':'2026-11-22','cluster_id':'residence_renewal'}]
            rows=mod.rank(self.report,self.catalog,temp,history,date(2026,11,23))
            renewal=next(x for x in rows if x['cluster_id']=='residence_renewal')
            self.assertTrue(renewal['cooldown_active'])
            self.assertEqual(renewal['recommended_action'],'MONITOR')
            selected,_=mod.select_for_v41(rows,history,date(2026,11,23))
            self.assertNotEqual(selected['cluster_id'],'residence_renewal')
    def test_cooldown_expires_after_60_days(self):
        self.assertFalse(mod.in_cooldown('residence_renewal',[{'selected_on':'2026-09-20','cluster_id':'residence_renewal'}],date(2026,11,23)))
    def test_material_change_can_override_cooldown(self):
        self.assertFalse(mod.in_cooldown('residence_renewal',[{'selected_on':'2026-11-22','cluster_id':'residence_renewal','material_legal_change_verified':True}],date(2026,11,23)))
    def test_no_unrelated_service(self):
        rep=json.loads(json.dumps(self.report))
        rep['windows']['28'].append({'id':'unrelated_car_insurance','impressions':9999,'clicks':50,'average_position':2,'representative_queries':[{'query':'seguro coche','impressions':9999}]})
        with tempfile.TemporaryDirectory() as temp:
            rows=mod.rank(rep,self.catalog,temp,[],date(2026,11,23))
        self.assertFalse(any(x['cluster_id']=='unrelated_car_insurance' for x in rows))
    def test_calendar_no_duplicate_topics(self):
        with tempfile.TemporaryDirectory() as temp:
            rows=mod.rank(self.report,self.catalog,temp,[],date(2026,11,23))
        cal=mod.plan(rows,date(2026,11,23),[])
        self.assertEqual(len({x['cluster_id'] for x in cal}),len(cal))
        self.assertTrue(all(date.fromisoformat(x['planned_date']).weekday() in (0,2,4) for x in cal))
        self.assertTrue(all(x['status']=='DRAFT_CANDIDATE_NOT_APPROVED' for x in cal))
    def test_v41_proposal_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            rows=mod.rank(self.report,self.catalog,temp,[],date(2026,11,23))
        selected,p=mod.select_for_v41(rows,[],date(2026,11,23))
        self.assertTrue(selected)
        self.assertEqual(p['version'],3)
        self.assertEqual(len(p['proposals']),1)
        self.assertEqual(p['proposals'][0]['action'],'improve_existing_page')
    def test_existing_page_not_new_article(self):
        with tempfile.TemporaryDirectory() as temp:
            blog=Path(temp)/'blog';blog.mkdir()
            (blog/'renovar-residencia-espana.html').write_text('existing')
            rows=mod.rank(self.report,self.catalog,temp,[],date(2026,11,23))
            r=next(x for x in rows if x['cluster_id']=='residence_renewal')
            self.assertEqual(r['recommended_action'],'IMPROVE_EXISTING_ARTICLE')
    def test_fails_closed_on_history_api_outage(self):
        # Never replaces a required artifact history with an empty record on API failures.
        import unittest.mock as mock
        with mock.patch.dict('os.environ',{'GITHUB_REPOSITORY':'owner/repo','GH_HISTORY_TOKEN':'fake'}):
            with mock.patch('urllib.request.OpenerDirector.open',side_effect=TimeoutError()):
                with self.assertRaises(RuntimeError):mod.load_prior_artifact()
    def test_cross_host_artifact_redirect_drops_auth(self):
        # Exercise the actual redirect handler installed by load_prior_artifact.
        import unittest.mock as mock
        import urllib.request
        import urllib.error
        import io

        class FakeResponse:
            def __init__(self, data): self.data=data
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return self.data
        seen=[]
        def mocked_open(opener, req, timeout=25):
            seen.append(req)
            if req.full_url.startswith('https://api.github.com/'):
                if req.full_url.endswith('/actions/artifacts?name=lexgo-v42-results&per_page=100'):
                    payload={'artifacts':[{'archive_download_url':'https://api.github.com/archive', 'created_at':'2026-11-22T00:00:00Z','expired':False}]}
                    return FakeResponse(json.dumps(payload).encode())
                # Simulate API redirect to GitHub's signed artifact storage.
                redirect = next(h for h in opener.handlers if isinstance(h, urllib.request.HTTPRedirectHandler))
                storage=redirect.redirect_request(req,None,302,'Found',{},'https://objects.githubusercontent.com/temporary-artifact.zip?sig=fake')
                seen.append(storage)
                raise urllib.error.HTTPError(req.full_url,401,'Simulated signed URL expiry',{},None)
            raise AssertionError('Unexpected URL')
        with mock.patch.dict('os.environ',{'GITHUB_REPOSITORY':'owner/repo','GH_HISTORY_TOKEN':'fake'}):
            with mock.patch('urllib.request.OpenerDirector.open',mocked_open):
                with self.assertRaisesRegex(RuntimeError,'HTTPError'):
                    mod.load_prior_artifact()
        self.assertGreaterEqual(len(seen),3)
        self.assertIn('Authorization',seen[-2].headers)
        self.assertNotIn('Authorization',seen[-1].headers)

    def test_score_breakdown_consistent(self):
        with tempfile.TemporaryDirectory() as temp:
            rows=mod.rank(self.report,self.catalog,temp,[],date(2026,11,23))
        for r in rows:self.assertEqual(r['score'],max(0,sum(v if k!='cooldown_penalty' else -v for k,v in r['score_breakdown'].items())))

if __name__=='__main__':unittest.main()
