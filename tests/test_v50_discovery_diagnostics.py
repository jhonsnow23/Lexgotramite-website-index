"""Local deterministic regression cases. Synthetic XML; NOT live BOE fixtures."""
import sys,unittest,xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import legal_relevance_v50 as m
import legal_content_v50 as content

class DiscoveryDiagnosticsTests(unittest.TestCase):
 def test_index_parser_reports_zero_provisions(self):
  root=ET.fromstring('<indice><metadata>no articles</metadata></indice>')
  found,diag=m.discover('renewal','renovacion residencia permanente',index_fetch=lambda u:(root,'x'))
  self.assertEqual(found,[])
  self.assertEqual(diag[0]['failure_code'],'BOE_INDEX_PARSING_FAILURE')
  self.assertEqual(diag[0]['index_articles'],0)
 def test_index_parsed_but_no_match(self):
  root=ET.fromstring('<indice><bloque id="xyz1" titulo="Artículo 1. Entrada por puestos fronterizos"/></indice>')
  found,diag=m.discover('renewal','renovacion de residencia permanente',index_fetch=lambda u:(root,'x'))
  self.assertEqual(found,[])
  self.assertEqual(diag[0]['index_articles'],1)
  self.assertEqual(diag[0]['failure_code'],'NO_RELEVANT_CANDIDATES')
 def test_synonym_long_term_vs_card(self):
  root=ET.fromstring('<indice><bloque id="legal22" titulo="Artículo 22. Tarjeta de identidad de extranjero"/><bloque id="legal23" titulo="Artículo 23. Entrada por frontera"/></indice>')
  found,diag=m.discover('renewal','renovacion residencia permanente',index_fetch=lambda u:(root,'x'))
  self.assertEqual([x['article'] for x in found],['22'])
 def test_full_text_rejects_border(self):
  result=m.provision_relevance('renewal','renovacion residencia permanente','Artículo 1. Entrada por puestos fronterizos. Un extranjero deberá acreditar su residencia para entrar en el territorio.',m.questions('renewal'))
  self.assertFalse(result['relevant'])
 def test_full_text_accepts_card_candidate(self):
  text='Artículo 22. La tarjeta de identidad de extranjero acreditará la situación de residencia. Su renovación se solicitará con la documentación indicada.'
  result=m.provision_relevance('renewal','renovacion residencia permanente',text,m.questions('renewal'))
  self.assertTrue(result['relevant'])
  self.assertIn('scope',result['matched_questions'])
 def test_documented_full_text_rejection(self):
  c={'source_id':'BOE-A-2024-24099','article':'1','title':'Artículo 1', 'score':0.5,'question_scores':{}}
  response={'official_url':'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099','provisions':[{'source_id':c['source_id'],'article':'1','text':'Entrada por frontera. Pasaporte en vigor para viajeros.','api_url':'https://www.boe.es/x','retrieved_at':'2026-11-23T00:00:00Z'}]}
  def discovery(group,topic):return [c],[]
  evidence,errors,diagnostics=content.retrieve_evidence({'group':'renewal','topic':'renovacion residencia permanente','research_questions':m.questions('renewal')},retrieval=lambda *args:response,discovery=discovery,return_diagnostics=True)
  self.assertEqual(evidence,[])
  self.assertEqual(errors[0]['category'],'RELEVANCE_FILTER_REJECTED_ALL')
  self.assertEqual(diagnostics['provision_attempts'][0]['stage'],'REJECTED_FULL_TEXT')
 def test_nationality_index_relevance(self):
  root=ET.fromstring('<indice><bloque id="nat22" titulo="Artículo 22. Nacionalidad española por residencia"/><bloque id="nat23" titulo="Artículo 23. Entrada por frontera"/></indice>')
  found,diag=m.discover('nationality','nacionalidad por residencia',index_fetch=lambda u:(root,'x'))
  self.assertTrue(any(x['article']=='22' for x in found))
  self.assertFalse(any(x['article']=='23' for x in found))
 def test_arraigo_index_relevance(self):
  root=ET.fromstring('<indice><bloque id="arra1" titulo="Artículo 100. Residencia por circunstancias excepcionales: arraigo sociolaboral"/><bloque id="bord1" titulo="Artículo 1. Control de fronteras"/></indice>')
  found,diag=m.discover('arraigo','arraigo sociolaboral',index_fetch=lambda u:(root,'x'))
  self.assertEqual([x['article'] for x in found],['100'])
 def test_plan_no_blog_body_access(self):
  p={'proposals':[{'cluster_id':'long_term_residence','proposed_title':'Renovacion residencia permanente', 'action':'create_article'}]}
  self.assertFalse(content.plan(p)['duplicate_metadata'])

if __name__=='__main__':unittest.main()
