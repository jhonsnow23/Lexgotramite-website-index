import json
from pathlib import Path
import tempfile
import unittest
from scripts.seo_v4_demo import build, SOURCE_MAP

class PreviewTests(unittest.TestCase):
    def test_preview_never_publishes(self):
        with tempfile.TemporaryDirectory() as d:
            result=build([{'id':'01-example','cluster_id':'residence_renewal','proposed_title':'Test','sections_to_research':['A'],'faq_questions':['B']}],d,fetcher=lambda url:{'url':url,'retrieved_at':'2026-11-22','sample':'x'*400,'length':400,'fetch_status':'retrieved_not_legally_verified'})
            self.assertFalse(result['publication_allowed'])
            self.assertTrue((Path(d)/'01-example.preview.html').exists())
            self.assertNotIn('blog/',str(list(Path(d).iterdir())))
            self.assertIn('noindex,nofollow',(Path(d)/'01-example.preview.html').read_text())
            e=json.loads((Path(d)/'01-example.evidence.json').read_text())
            self.assertFalse(e['publication_allowed'])
    def test_network_error_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            result=build([{'id':'02-test','cluster_id':'nationality'}],d,fetcher=lambda url: (_ for _ in ()).throw(OSError('offline')))
            self.assertEqual(result['proposals'][0]['sources_retrieved'],0)
            self.assertFalse(result['proposals'][0]['publishable'])
    def test_all_source_urls_official(self):
        from scripts.v4_validate import is_official
        for group in SOURCE_MAP.values():
            for _,url in group:self.assertTrue(is_official(url))
if __name__=='__main__':unittest.main()
