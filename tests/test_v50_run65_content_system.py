"""Offline routing, budget and research tests. Synthetic publication fixtures stay in temp dirs."""
import copy, io, json, shutil, tempfile, unittest, zipfile, subprocess
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
from test_v50_run55_first_article import engine, ArchivedResearch, response, verdict, Replay
import knowledge_hub_v50 as hub
import weekly_content_v50 as weekly
import prepare_publication_v50 as prepare
ROOT=Path(__file__).resolve().parents[1]

def fixture(folder,kind='KNOWLEDGE_ARTICLE',simulated=False):
    topic='Renovación de residencia no lucrativa: ejemplo de prueba' if kind=='KNOWLEDGE_ARTICLE' else weekly.TITLES['no_lucrativa']
    article={'title':topic,'article_type':'specific_question' if kind=='KNOWLEDGE_ARTICLE' else 'information','introduction':'','intro_claim':True,'sections':[{'heading':'Introducción','paragraphs':[{'claim_id':'C_test','text':'Texto sintético de prueba. '* (4 if kind=='KNOWLEDGE_ARTICLE' else 55),'conditions':'','exceptions':'','citations':[{'url':'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099','label':'Artículo de prueba','passage_id':'P_test'}]}]}],'limitations':[],'disclaimer':'Información general de prueba.','contact_url':None,'publication_allowed':False,'human_legal_review_required':True}
    h=engine.digest(article);article.update(content_hash=h,automated_review_passed=True,simulated=simulated,legal_accuracy_certified=False)
    meta={'category':'no_lucrativa','topic':topic,'meta_description':'Descripción de prueba.','origin':'EDITORIAL_SEED','primary_search_query':topic}
    if kind=='WEEKLY_BLOG':meta.update(origin='EDITORIAL_SYNTHESIS',weekly_context=[{'category':'no_lucrativa','topic':'Pregunta de prueba'}])
    folder.mkdir(parents=True,exist_ok=True)
    for name,value in [('article',article),('article_metadata',meta),('legal_review',{'article_hash':h,'passed':True,'simulated':simulated,'verdict':{'approved':True,'claim_checks':[{'claim_id':'C_test','supported':True}],'prior_defect_checks':[],'defects':[],**{k:True for k in engine.CHECKS}}}),('decision',{'result':'REVIEW_READY','simulated':simulated})]:hub.save(folder/(name+'.json'),value)
    return folder

class ContentSystem(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'site';self.root.mkdir()
        for f in ('index.html','sitemap.xml','publish_state.json'):shutil.copy(ROOT/f,self.root/f)
        shutil.copytree(ROOT/'blog',self.root/'blog');(self.root/'guias').mkdir();shutil.copy(ROOT/'guias/knowledge.css',self.root/'guias/knowledge.css')
        hub.save(self.root/hub.INVENTORY,[])
        self.folder=Path(self.tmp.name)/'draft'
    def tearDown(self):self.tmp.cleanup()
    def test_exact_placement_empty_and_idempotent(self):
        hub.render_hub(self.root);h=(self.root/'index.html').read_text();self.assertLess(h.index('id="galeria"'),h.index('id="guias-renovacion"'));self.assertLess(h.index('id="guias-renovacion"'),h.index('id="resenas"'))
        self.assertEqual(h.count('class="lg-guide-card"'),6);self.assertNotIn('Consultar guía',hub.home_section([]));self.assertIn('noindex,follow',(self.root/'guias/renovaciones-residencia-espana/index.html').read_text())
        self.assertNotIn(hub.BASE,(self.root/'sitemap.xml').read_text());hub.render_hub(self.root);self.assertEqual(h,(self.root/'index.html').read_text())
    def test_requires_human_hash_and_rejects_simulation(self):
        fixture(self.folder);before=(self.root/'index.html').read_text()
        with self.assertRaises(ValueError):hub.publish(self.folder,'wrong',self.root)
        self.assertEqual(before,(self.root/'index.html').read_text());fixture(self.folder,simulated=True)
        with self.assertRaises(ValueError):hub.approved_source(self.folder)
    def test_tampering_invalidates_review(self):
        fixture(self.folder);a=hub.read(self.folder/'article.json');a['sections'][0]['paragraphs'][0]['text']='Changed';hub.save(self.folder/'article.json',a)
        with self.assertRaises(ValueError):hub.approved_source(self.folder)
    def test_daily_short_answer_goes_into_category_not_blog(self):
        fixture(self.folder);before=(self.root/'blog/index.html').read_text();a,m,k,h=hub.approved_source(self.folder);r=hub.publish(self.folder,h,self.root)
        self.assertEqual(k,'KNOWLEDGE_ARTICLE');self.assertIn('#',r['url']);self.assertEqual(before,(self.root/'blog/index.html').read_text())
        cat=(self.root/'guias/renovacion-residencia-no-lucrativa/index.html').read_text();self.assertIn(a['title'],cat);self.assertIn('https://www.boe.es/',cat);self.assertIn(r['url'],(self.root/'index.html').read_text())
        self.assertIn(hub.SITE+hub.BASE,(self.root/'sitemap.xml').read_text());self.assertNotIn(r['url'],(self.root/'sitemap.xml').read_text())
        with self.assertRaises(ValueError):hub.publish(self.folder,h,self.root)
    def test_weekly_routes_to_existing_blog(self):
        fixture(self.folder);_,_,_,h=hub.approved_source(self.folder);daily=hub.publish(self.folder,h,self.root)
        fixture(self.folder,'WEEKLY_BLOG');_,_,_,h=hub.approved_source(self.folder)
        with patch.multiple(hub.blog,ROOT=self.root,BLOG_DIR=self.root/'blog',STATE_FILE=self.root/'publish_state.json',BLOG_INDEX_FILE=self.root/'blog/index.html',HOME_FILE=self.root/'index.html'):
            r=hub.publish(self.folder,h,self.root)
        self.assertTrue(r['url'].startswith('/blog/'));content=(self.root/(r['url'].strip('/')+'.html')).read_text();self.assertIn('https://www.boe.es/',content);self.assertIn(daily['url'],content)
        self.assertIn(r['url'],(self.root/'blog/index.html').read_text());self.assertNotIn(r['title'],hub.home_section(hub.inventory(self.root)))
    def test_budget_duplicate_and_abandoned_reservation(self):
        day=date(2026,11,26);r=weekly.calculate('daily',day,day,5,1,[],[],'1');self.assertEqual(r['reserved_usd'],.15)
        same=weekly.calculate('daily',day,day,5,1,[r],[],'2');self.assertFalse(same['allowed'])
        next_=weekly.calculate('weekly',day,day,5,1,[r],[],'2');self.assertAlmostEqual(next_['reserved_usd'],.20)
        s={'run_id':'1','kind':'daily','date':day.isoformat(),'debit_usd':.03};next_=weekly.calculate('weekly',day,day,5,1,[r],[s],'2');self.assertEqual(next_['reserved_usd'],.25)
        with self.assertRaises(ValueError):weekly.calculate('daily',day+timedelta(days=80),day,5,1,[],[],'2')
    def test_budget_low_balance_and_weekly_slot(self):
        day=date(2026,11,26);self.assertFalse(weekly.calculate('daily',day,day,.02,1,[],[],'1')['allowed'])
        r=weekly.calculate('weekly',day,day,5,1,[],[],'1');self.assertFalse(weekly.calculate('weekly',day+timedelta(days=1),day,5,1,[r],[],'2')['allowed'])
    def test_settlement_without_completed_summary_reserves_full_amount(self):
        day=date(2026,11,26);r=weekly.calculate('daily',day,day,5,1,[],[],'1');p=self.folder/'reservation.json';hub.save(p,r);out=self.folder/'settlement.json';weekly.settle(p,self.folder/'missing.json',out);self.assertEqual(hub.read(out)['debit_usd'],.15)
    def test_weekly_scope_and_no_fabricated_demand(self):
        records=[{'category':'no_lucrativa','topic':'Pregunta de prueba','search_demand_evidence':{'impressions':20}},{'category':'cuenta_ajena','topic':'Otra pregunta'}];p=weekly.choose_weekly(records);self.assertEqual(p['category'],'no_lucrativa');self.assertEqual(len(p['research_history']),1);self.assertFalse(p['search_demand_verified']);self.assertNotEqual(weekly.choose_weekly(records,prior_topics=[p['title']])['title'],p['title'])
    def test_weekly_engine_end_to_end_replay(self):
        replay=Replay();weekly_context=[{'category':'no_lucrativa','topic':'Renovación de residencia no lucrativa: plazo de solicitud','article_refs':[{'document':engine.RD,'article':63}]}]
        result=engine.run(self.folder,category='no_lucrativa',topic=weekly.TITLES['no_lucrativa'],article_type='information',bootstrap=False,weekly_context=weekly_context,transport=replay,researcher_factory=ArchivedResearch,limits=engine.Limits(topics=1,research_rounds=1,draft_repairs=0))
        self.assertEqual(result['result'],'SIMULATED_REVIEW_PASS',result);self.assertEqual(result['articles_independently_approved'],0)
        self.assertEqual(replay.inputs[0][1]['weekly_research_questions'],[weekly_context[0]['topic']]);self.assertEqual(replay.review_calls,1)
        self.assertIn('63',{r['article'] for r in hub.read(self.folder/'topic_01_no_lucrativa/evidence.json')})
    def test_budget_settlement_releases_unused_reservation(self):
        day=date(2026,11,26);r=weekly.calculate('daily',day,day,5,1,[],[],'1');p=self.folder/'reservation.json';hub.save(p,r)
        u={'calls':[{}],'publication_allowed':False,'conservative_budget_debit_usd':.03,'estimated_usd':.015};hub.save(self.folder/'api_usage.json',u);hub.save(self.folder/'run_summary.json',{'publication_allowed':False,'simulated':False,'api_calls':1,'conservative_budget_debit_usd':.03})
        out=self.folder/'settlement.json';weekly.settle(p,self.folder/'api_usage.json',out);self.assertEqual(hub.read(out)['debit_usd'],.03)
    def test_review_criterion_cannot_be_bypassed(self):
        fixture(self.folder);r=hub.read(self.folder/'legal_review.json');r['verdict'][engine.CHECKS[0]]=False;hub.save(self.folder/'legal_review.json',r)
        with self.assertRaises(ValueError):hub.approved_source(self.folder)
    def test_manual_prepare_inspect_and_patch_no_push(self):
        folder=fixture(self.folder);(folder/'article.md').write_text('Synthetic fixture; no real article.')
        out=Path(self.tmp.name)/'out';subprocess.run(['git','init','-q',str(self.root)],check=True)
        subprocess.run(['git','add','.'],cwd=self.root,check=True);subprocess.run(['git','-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline'],cwd=self.root,check=True)
        with patch.object(hub,'ROOT',self.root):
            prepare.prepare(folder,out,'daily','');self.assertFalse((out/'publication.patch').exists())
            h=hub.read(out/'approval-preview.json')['approval_hash'];prepare.prepare(folder,out,'daily',h)
        self.assertTrue((out/'publication.patch').is_file());self.assertTrue((out/'WEBSITE-FILES/index.html').is_file());self.assertFalse(hub.read(out/'prepared-publication.json')['live_publication_performed'])
    def test_manual_publication_workflow_never_pushes(self):
        s=(ROOT/'.github/workflows/lexgo-prepare-publication-v50.yml').read_text();self.assertIn('workflow_dispatch:',s);self.assertNotIn('schedule:',s);self.assertIn('contents: read',s);self.assertNotIn('contents: write',s);self.assertNotIn('OPENAI_API_KEY',s);self.assertIn('approval_hash',s)
    def test_workflows_read_only_and_reserve_first(self):
        for name in ('lexgo-seo-v50.yml','lexgo-weekly-blog-v50.yml'):
            s=(ROOT/'.github/workflows'/name).read_text();self.assertIn('contents: read',s);gen,pub=s.split('\n  publish:\n',1);self.assertNotIn('contents: write',gen);self.assertIn('contents: write',pub);self.assertNotIn('OPENAI_API_KEY:',pub);self.assertIn('group: lexgo-seo-engine-v50',s);self.assertLess(s.index('Persist reservation before generation'),s.index('OPENAI_API_KEY:'));self.assertIn('retention-days: 90',s)
if __name__=='__main__':unittest.main()
