import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SRC=Path(__file__).resolve().parents[1]/'scripts'/'seo_v41.py'
spec=importlib.util.spec_from_file_location('seo_v41',SRC)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
SOURCE={'id':'BOE-A-2024-24099','url':mod.BOE_LEGAL,'fetched_at':'2026-11-22T20:00:00+00:00','extract':'La autorización de residencia requerirá cumplir las condiciones que se establezcan en la normativa que resulte de aplicación. '*40}
QUOTE='La autorización de residencia requerirá cumplir las condiciones que se establezcan en la normativa que resulte de aplicación.'
ARTICLE={'title':'Guía sobre renovación de residencia y procedimientos vigentes','meta_description':'Guía para comprobar el procedimiento de residencia aplicable a cada supuesto personal.','introduction':'La autorización aplicable depende de cada situación. Es necesario verificar el trámite concreto.','sections':[{'heading':f'Aspecto {n}','paragraphs':['La normativa prevé requisitos distintos según el procedimiento.']*5} for n in range(4)],'faqs':[{'question':'¿Cómo se solicita?','answer':'Verifica el supuesto y el trámite.'}],'claims':[{'claim':'Hay condiciones aplicables a autorizaciones','source_id':SOURCE['id'],'evidence_excerpt':QUOTE}],'unresolved_questions':[]}
class Tests(unittest.TestCase):
 def test_allowlist(self):
  self.assertTrue(mod.is_official(mod.BOE_LEGAL))
  for url in ['http://www.boe.es','https://boe.es.evil.test/','https://evil.test/','https://www.boe.es@evil.test/']:
   self.assertFalse(mod.is_official(url))
 def test_proposal_selection(self):
  data={'version':3,'proposals':[{'cluster_id':'regularization_processing','action':'improve_existing_page'},{'cluster_id':'residence_renewal','action':'improve_existing_page'}]}
  self.assertEqual(mod.select_proposal(data)['cluster_id'],'residence_renewal')
 def test_reject_bad_proposal_version(self):
  with self.assertRaises(ValueError):mod.select_proposal({'version':2,'proposals':[]})
 def test_real_excerpt_is_found(self):
  v=mod.validate_draft(ARTICLE,[SOURCE]);self.assertEqual(v['exact_quotes_matched'],1)
  self.assertFalse(v['publication_allowed'])
 def test_fabricated_quote_blocks(self):
  a=json.loads(json.dumps(ARTICLE));a['claims'][0]['evidence_excerpt']='Texto falso que no consta en el BOE y no debe presentarse como una cita literal auténtica.'
  self.assertFalse(mod.validate_draft(a,[SOURCE])['schema_and_evidence_checks_passed'])
 def test_missing_claim_blocks(self):
  a={**ARTICLE,'claims':[]};self.assertTrue(mod.validate_draft(a,[SOURCE])['errors'])
 def test_unresolved_research_blocks(self):
  a={**ARTICLE,'unresolved_questions':['¿Cuál es la disposición transitoria?']};self.assertFalse(mod.validate_draft(a,[SOURCE])['schema_and_evidence_checks_passed'])
 def test_html_is_escaped_and_noindex(self):
  a={**ARTICLE,'title':'<script>alert(1)</script> Guía sobre la residencia'}
  html=mod.render(a,[SOURCE],{})
  self.assertNotIn('<script>',html);self.assertIn('noindex,nofollow',html);self.assertIn(mod.BOE_LEGAL,html)
 def test_model_requires_key(self):
  with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
   with self.assertRaisesRegex(RuntimeError,'OPENAI_API_KEY'):mod.openai_generate({},[SOURCE])
 def test_no_publication_even_on_mock_success(self):
  p={'version':3,'proposals':[{'cluster_id':'residence_renewal','action':'improve_existing_page','proposed_title':'Renovar residencia'}]}
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'proposals.json').write_text(json.dumps(p),encoding='utf8')
   out=root/'reports';mockfetch={'url':SOURCE['url'],'text':SOURCE['extract'],'fetched_at':SOURCE['fetched_at'],'sha256':'abc'}
   from argparse import Namespace
   with patch.object(mod,'fetch_official',return_value=mockfetch),patch.object(mod,'openai_generate',return_value=ARTICLE):
    result=mod.run(Namespace(proposals=str(root/'proposals.json'),output=str(out),model='gpt-4.1-mini'))
   self.assertEqual(result,0)
   self.assertFalse(json.loads((out/'decision.json').read_text())['publication_allowed'])
   self.assertFalse((root/'blog').exists());self.assertFalse((root/'publish_state.json').exists())
 def test_no_source_fail_closed(self):
  p={'version':3,'proposals':[{'cluster_id':'residence_renewal','action':'improve_existing_page','proposed_title':'Renovar residencia'}]}
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'p.json').write_text(json.dumps(p),encoding='utf8')
   from argparse import Namespace
   with patch.object(mod,'fetch_official',side_effect=ValueError('403')):
    ret=mod.run(Namespace(proposals=str(root/'p.json'),output=str(root/'out'),model='gpt-4.1-mini'))
   self.assertEqual(ret,1)
   self.assertFalse(json.loads((root/'out'/'decision.json').read_text())['publication_allowed'])
 def test_intro_list_paragraphs_render_correctly(self):
  a={**ARTICLE,'introduction':['Primer párrafo explicativo suficientemente detallado sobre el trámite.', 'Segundo párrafo explicativo igualmente detallado sobre requisitos.']}
  result=mod.validate_draft(a,[SOURCE])
  self.assertNotIn('Incomplete introduction',result['errors'])
  markup=mod.render(a,[SOURCE],{})
  self.assertIn('<p>Primer párrafo',markup)
  self.assertIn('<p>Segundo párrafo',markup)
  self.assertNotIn('&amp;#x27;',markup)
 def test_failed_validation_reports_reasons(self):
  p={'version':3,'proposals':[{'cluster_id':'residence_renewal','action':'improve_existing_page','proposed_title':'Renovar residencia'}]}
  bad={**ARTICLE,'unresolved_questions':['Falta investigar un supuesto']}
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'p.json').write_text(json.dumps(p),encoding='utf8')
   from argparse import Namespace
   mockfetch={'url':SOURCE['url'],'text':SOURCE['extract'],'fetched_at':SOURCE['fetched_at'],'sha256':'abc'}
   with patch.object(mod,'fetch_official',return_value=mockfetch),patch.object(mod,'openai_generate',return_value=bad):
    ret=mod.run(Namespace(proposals=str(root/'p.json'),output=str(root/'out'),model='gpt-4.1-mini'))
   self.assertEqual(ret,1)
   self.assertIn('Outstanding legal research questions',json.loads((root/'out'/'decision.json').read_text())['reasons'])
if __name__=='__main__':unittest.main()
