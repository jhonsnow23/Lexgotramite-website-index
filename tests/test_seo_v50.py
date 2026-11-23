import importlib.util
import copy
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

    def test_existing_article_metadata_blocks_new_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'blog';folder.mkdir()
            old=folder/'tipos-de-residencia-en-espana.html'
            old.write_text('UNTRUSTED OLD BLOG CONTENT MUST NOT ENTER THE MODEL',encoding='utf-8')
            # Explicitly model a same-intent REAL query; the general test
            # fixture otherwise has synthetic, unrelated query text.
            report=copy.deepcopy(self.report)
            for cluster in report['windows']['28']:
                if cluster['id']=='residency_options':
                    cluster['representative_queries']=[{'query':'tipos de residencia en España','impressions':14}]
            rows,winner,_=mod.choose(report,self.catalog,tmp,[],date(2026,11,23))
            matching=next(r for r in rows if r['cluster_id']=='residency_options')
            self.assertEqual(matching['recommended_action'],'SKIP')
            self.assertIn('metadata-only',matching['selection_reason'])

    def test_metadata_only_does_not_read_blog_body(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'blog';folder.mkdir()
            (folder/'renovar-residencia-espana.html').write_text('SENSITIVE BLOG BODY')
            original=Path.read_text
            def deny_html(path,*args,**kwargs):
                if path.suffix=='.html':
                    raise AssertionError('Tried to read existing blog content')
                return original(path,*args,**kwargs)
            with patch.object(Path,'read_text',deny_html):
                rows,winner,_=mod.choose(self.report,self.catalog,tmp,[],date(2026,11,23))
                self.assertEqual(len(rows),8)

    def test_distinct_specific_query_not_blocked_by_generic_blog(self):
        topic={'proposed_title':'Renovación de residencia permanente: requisitos',
               'primary_query':'renovación residencia permanente'}
        duplicate,reason,path=mod.classify_duplicate(topic,['blog/renovar-residencia-espana.html'])
        self.assertFalse(duplicate)
        self.assertTrue(path.startswith('blog/'))

    def test_same_query_as_blog_is_duplicate(self):
        topic={'proposed_title':'Renovar residencia en España',
               'primary_query':'renovar residencia España'}
        duplicate,_,_=mod.classify_duplicate(topic,['blog/renovar-residencia-espana.html'])
        self.assertTrue(duplicate)

    def test_service_landing_url_does_not_auto_block(self):
        topic={'proposed_title':'Documentos para solicitar nacionalidad por residencia',
               'primary_query':'documentación nacionalidad española'}
        duplicate,_,_=mod.classify_duplicate(topic,['nacionalidad-espanola.html'])
        self.assertFalse(duplicate)

    def test_same_url_different_cluster_does_not_impose_backoff(self):
        hist=[{'cluster_id':'nationality_requirements','existing_page':'nacionalidad-espanola.html',
               'date':'2026-11-23','status':'DRAFT_FAILED'}]
        item={'cluster_id':'nationality_documents','existing_pages':['nacionalidad-espanola.html']}
        self.assertIsNone(mod.topic_blocker(item,hist,date(2026,11,23)))

    def test_distinct_new_proposal_cannot_rewrite_old_page(self):
        topic={'cluster_id':'nationality_documents','proposed_title':'Documentos de nacionalidad',
               'supporting_queries':['documentos nacionalidad'],'impressions_28d':4,'impressions_90d':48}
        _,proposal=mod.supports_research(topic)
        self.assertEqual(proposal['proposals'][0]['action'],'create_article')
        self.assertNotIn('existing_pages',proposal['proposals'][0])

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
