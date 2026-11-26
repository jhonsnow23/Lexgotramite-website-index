"""Synthetic offline tests; no paid API or publication outside temp repos."""
import os, shutil, subprocess, tempfile, unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from test_v50_run65_content_system import fixture, ROOT, hub, engine, weekly
import autonomous_publisher_v50 as auto
import evidence_passages_v50 as passages

class Autonomous(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'site';self.folder=Path(self.tmp.name)/'draft';self.root.mkdir()
        for f in [*ROOT.glob('*.html'),ROOT/'sitemap.xml',ROOT/'publish_state.json']:shutil.copy(f,self.root/f.name)
        shutil.copytree(ROOT/'blog',self.root/'blog');shutil.copytree(ROOT/'guias',self.root/'guias')
        hub.render_hub(self.root)
        subprocess.run(['git','init','-q',str(self.root)],check=True);auto.git(self.root,'add','.');auto.git(self.root,'-c','user.name=test','-c','user.email=test@example.invalid','commit','-qm','baseline')
        self.env=patch.dict(os.environ,{'LEXGO_AUTOPUBLISH_ENABLED':'true'});self.env.start()
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def draft(self,kind='KNOWLEDGE_ARTICLE'):
        fixture(self.folder,kind);a=hub.read(self.folder/'article.json');m=hub.read(self.folder/'article_metadata.json');m['publication_allowed']=False;hub.save(self.folder/'article_metadata.json',m)
        p=a['sections'][0]['paragraphs'][0]
        e={'evidence_id':'EV_TEST','source_id':engine.RD,'authority':'boe','article':'64','official_url':p['citations'][0]['url'],'document_title':'Synthetic test provision','retrieved_at':'2026-11-26T08:00:00+00:00','text':'Texto sintético utilizado exclusivamente para comprobar la integridad del publicador.'}
        catalog=passages.build_catalog([e]);pid=next(iter(catalog['passages']));p['citations'][0]['passage_id']=pid
        a['content_hash']=engine.digest({k:v for k,v in a.items() if k not in ('content_hash','automated_review_passed','simulated','legal_accuracy_certified')});hub.save(self.folder/'article.json',a)
        r=hub.read(self.folder/'legal_review.json');r['article_hash']=a['content_hash'];hub.save(self.folder/'legal_review.json',r)
        hub.save(self.folder/'evidence.json',[e]);hub.save(self.folder/'evidence_passage_catalog.json',catalog);hub.save(self.folder/'citation_validation_report.json',[]);hub.save(self.folder/'passage_aliases.json',{'P001':pid})
        hub.save(self.folder/'claim_evidence_matrix.json',{'publication_allowed':False,'claims':[{'claim_id':p['claim_id'],'claim':p['text'],'section':a['sections'][0]['heading'],'conditions':p['conditions'],'exceptions':p['exceptions'],'verification':'AUTOMATED_REVIEW_SUPPORTED','passages':[passages.resolve_passage(pid,catalog,[e])],'evidence_ids':['EV_TEST']}]})
        hub.save(self.folder/'editorial_quality_report.json',{'article_hash':a['content_hash'],'simulated':False,'independent_review_passed':True})
        return auto.validate_evidence(self.folder)
    def prepare(self,kind='daily',rid='123'):
        a,m,k,h,r=auto.validate_evidence(self.folder);return auto.prepare(self.folder,self.root,kind,rid,'2026-11-26',r,engine.digest(hub.read(self.folder/'legal_review.json')))
    def test_daily_route_hash_and_no_other_content(self):
        self.draft();before=(self.root/'blog/index.html').read_bytes();row,files,state=self.prepare()
        self.assertEqual(state,'WEBSITE_VALIDATION_PASSED');self.assertIn('#',row['url']);self.assertFalse(row['human_approved']);self.assertEqual(row['publication_policy'],auto.POLICY);self.assertEqual(before,(self.root/'blog/index.html').read_bytes());self.assertNotIn('blog/index.html',files);self.assertIn(row['content_hash'],auto.url_file(self.root,row['url']).read_text())
    def test_weekly_routes_to_existing_blog(self):
        self.draft('WEEKLY_BLOG');row,files,state=self.prepare('weekly');self.assertTrue(row['url'].startswith('/blog/'));self.assertIn('blog/index.html',files);self.assertIn(row['content_hash'],auto.url_file(self.root,row['url']).read_text());self.assertNotIn(row['title'],hub.home_section(hub.inventory(self.root)))
    def test_disabled_never_mutates(self):
        self.draft()
        with patch.dict(os.environ,{'LEXGO_AUTOPUBLISH_ENABLED':'false'}), self.assertRaises(ValueError):self.prepare()
        self.assertFalse(auto.changed(self.root))
    def test_negative_review(self):
        self.draft();r=hub.read(self.folder/'legal_review.json');r['verdict']['no_misleading_omissions']=False;hub.save(self.folder/'legal_review.json',r)
        with self.assertRaises(ValueError):auto.validate_evidence(self.folder)
    def test_simulation_rejected(self):
        self.draft();a=hub.read(self.folder/'article.json');a['simulated']=True;hub.save(self.folder/'article.json',a)
        with self.assertRaises(ValueError):auto.validate_evidence(self.folder)
    def test_tampered_evidence_rejected(self):
        self.draft();e=hub.read(self.folder/'evidence.json');e[0]['text']+='Altered';hub.save(self.folder/'evidence.json',e)
        with self.assertRaises(ValueError):auto.validate_evidence(self.folder)
    def test_tampered_matrix_rejected(self):
        self.draft();m=hub.read(self.folder/'claim_evidence_matrix.json');m['claims'][0]['claim']='Altered';hub.save(self.folder/'claim_evidence_matrix.json',m)
        with self.assertRaises(ValueError):auto.validate_evidence(self.folder)
    def test_wrong_destination_rejected(self):
        self.draft()
        with self.assertRaises(ValueError):self.prepare('weekly')
    def test_duplicate_after_commit(self):
        self.draft();row,files,state=self.prepare();auto.git(self.root,'add','--',*files);auto.git(self.root,'-c','user.name=test','-c','user.email=test@example.invalid','commit','-qm','published');self.assertEqual(self.prepare()[2],'ALREADY_COMMITTED')
    def test_budget_requires_settlement_and_real_review(self):
        res=weekly.calculate('daily',date(2026,11,26),date(2026,11,26),5,1,[],[],'123');st={'kind':'daily','run_id':'123','date':res['date'],'debit_usd':.03,'estimated_cost_usd':.015,'publication_allowed':False};summary={'result':'REVIEW_READY','simulated':False,'articles_independently_approved':1,'api_calls':2,'conservative_budget_debit_usd':.03,'estimated_cost_usd':.015,'publication_allowed':False};usage={'calls':[{'stage':'research','status':'COMPLETED'},{'stage':'legal_review','status':'COMPLETED'}],'conservative_budget_debit_usd':.03,'estimated_usd':.015,'publication_allowed':False}
        self.assertEqual(auto.validate_budget(res,st,summary,usage,'daily','123'),res['slot']);st['debit_usd']=.16
        with self.assertRaises(ValueError):auto.validate_budget(res,st,summary,usage,'daily','123')
    def test_run_origin(self):
        data={'id':123,'head_branch':'main','head_repository':{'full_name':auto.REPO},'path':'.github/workflows/lexgo-seo-v50.yml','event':'schedule','status':'completed'};self.assertEqual(auto.validate_run(data,'daily','1'),'123');data['head_branch']='other'
        with self.assertRaises(ValueError):auto.validate_run(data,'daily','1')
    def test_native_schedules_and_separate_permissions(self):
        for f,cron in [('lexgo-seo-v50.yml','15 8 * * *'),('lexgo-weekly-blog-v50.yml','15 18 * * 0')]:
            s=(ROOT/'.github/workflows'/f).read_text();gen,pub=s.split('\n  publish:\n',1);self.assertIn(cron,gen);self.assertIn("timezone: 'Europe/Madrid'",gen);self.assertNotIn('contents: write',gen);self.assertIn('contents: write',pub);self.assertNotIn('OPENAI_API_KEY',pub);self.assertIn('LEXGO_AUTOPUBLISH_ENABLED',pub)
    def test_backlog_rejects_unlisted_article(self):
        self.draft()
        with self.assertRaises(ValueError):auto.validate_evidence(self.folder,True)
    def test_monitor_reports_changed_source_without_mutating_site(self):
        self.draft();row,files,_=self.prepare();before=(self.root/'index.html').read_bytes();out=Path(self.tmp.name)/'monitor.json'
        with patch.object(auto,'fresh_sources',side_effect=ValueError('changed')),patch.object(auto,'verify_live',return_value=False):auto.monitor(self.root,out)
        report=hub.read(out);self.assertEqual(report['checks'][0]['state'],'REVALIDATION_REQUIRED');self.assertFalse(report['deployment_rechecks'][0]['public_url_verified']);self.assertEqual(before,(self.root/'index.html').read_bytes())
    def test_freshness_change_blocks(self):
        a,m,k,h,refs=self.draft()
        with patch.object(engine.OfficialResearch,'article',return_value=[{'source_id':engine.RD,'article':'64','text':'different'}]), self.assertRaises(ValueError):auto.fresh_sources(refs,self.tmp.name)
if __name__=='__main__':unittest.main()
