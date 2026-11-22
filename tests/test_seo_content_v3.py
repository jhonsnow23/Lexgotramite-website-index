import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'scripts'/'seo_content_v3.py'
spec=importlib.util.spec_from_file_location('seo_content_v3',SOURCE)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ContentV3Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'blog').mkdir()
        (self.root/'blog'/'renovar-residencia-espana.html').write_text('<title>Renovar residencia</title><meta name="description" content="Old">',encoding='utf-8')
        (self.root/'residencia-espana.html').write_text('<title>Residencia España</title>',encoding='utf-8')
        self.report={'version':2,'metadata':{'source':'google_search_console_api','data_end_date':'2026-11-19'},
          'windows':{'28':[{'id':'residence_renewal','title':'Renovación de residencia','impressions':81,'clicks':0,'representative_queries':[{'query':'renovar residencia'}]}]},
          'editorial_calendar':[{'rank':1,'cluster':'Renovación de residencia','priority_score':88,'existing_page':'blog/renovar-residencia-espana.html'}]}
    def test_existing_page_is_not_duplicated(self):
        p=mod.generate(self.report,self.root)['proposals'][0]
        self.assertEqual(p['action'],'improve_existing_page')
        self.assertEqual(p['target_page'],'blog/renovar-residencia-espana.html')
        self.assertFalse(p['publication_allowed'])
    def test_missing_page_blocks_new_draft(self):
        self.report['editorial_calendar'][0]['existing_page']='blog/missing.html'
        p=mod.generate(self.report,self.root)['proposals'][0]
        self.assertEqual(p['action'],'manual_review_missing_existing_page')
        self.assertFalse(p['publication_allowed'])
    def test_generated_md_requires_review(self):
        p=mod.generate(self.report,self.root)['proposals'][0]
        md=mod.render_markdown(p)
        self.assertIn('NO PUBLICAR',md)
        self.assertIn('PENDIENTE',md)
        self.assertIn('Aprobación explícita',md)
    def test_related_links_are_existing_pages(self):
        p=mod.generate(self.report,self.root)['proposals'][0]
        self.assertEqual(p['related_internal_links'][0]['path'],'residencia-espana.html')
    def test_reject_path_traversal(self):
        self.assertIsNone(mod.load_page(self.root,'../secrets.html'))
        self.assertIsNone(mod.internal_target(self.root,'/../../etc/passwd'))
    def test_refuses_non_v2(self):
        with self.assertRaises(ValueError): mod.generate({'version':1},self.root)
    def test_no_publication_files_written(self):
        src=self.root/'report.json';src.write_text(json.dumps(self.report),encoding='utf-8')
        out=self.root/'reports'/'editorial_v3'
        mod.main(['--input',str(src),'--output',str(out),'--root',str(self.root)])
        self.assertTrue((out/'README.md').is_file())
        self.assertEqual(len(list(out.glob('*.md'))),2)
        self.assertFalse((self.root/'drafts').exists())
        self.assertFalse((self.root/'publish_state.json').exists())
        obj=json.loads((out/'proposals.json').read_text(encoding='utf-8'))
        self.assertFalse(obj['publication_allowed'])
    def test_unknown_source_rejected(self):
        self.report['metadata']['source']='unknown'
        with self.assertRaises(ValueError): mod.generate(self.report,self.root)

if __name__=='__main__':unittest.main()
