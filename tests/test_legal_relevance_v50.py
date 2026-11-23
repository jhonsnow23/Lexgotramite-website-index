import sys, unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import legal_relevance_v50 as mod
import legal_content_v50 as content

class LegalRelevanceTests(unittest.TestCase):
 def test_topic_groups(self):
  self.assertEqual(mod.group_of('residency_options','Tipos de residencia'),'residence')
  self.assertEqual(mod.group_of('nationality_requirements','Nacionalidad española'),'nationality')
  self.assertEqual(mod.group_of('arraigo','Arraigo sociolaboral'),'arraigo')
 def test_excludes_border_crossing(self):
  self.assertEqual(mod.score_title('Artículo 1 Entrada por puestos fronterizos','residencia temporal larga duración'),0)
 def test_relevant_heading(self):
  self.assertGreater(mod.score_title('Residencia de larga duración','tipos residencia temporal larga duración'),0)
 def test_index_block_id_from_official_fields_not_guess(self):
  root=ET.fromstring('<indice><bloque><id>art92x</id><titulo>Art 22 Residencia temporal</titulo></bloque></indice>')
  self.assertEqual(mod.parse_index_titles(root),[('22','art92x','Art 22 Residencia temporal')])
 def test_conflicting_heading_block_mapping_rejected(self):
  root=ET.fromstring('<indice><bloque id="a22" titulo="Art 22"/><bloque id="another22" titulo="Art 22"/></indice>')
  self.assertEqual(mod.parse_index_titles(root),[])
 def test_no_positional_fallback(self):
  root=ET.fromstring('<indice><bloque id="art1" titulo="Art 1 Entrada por puestos fronterizos"/><bloque id="art2" titulo="Art 2 Pasaporte"/></indice>')
  results,_=mod.discover('residence','Tipos de residencia',index_fetch=lambda url:(root,'hash'))
  self.assertEqual(results,[])
 def test_unknown_evidence_id_does_not_pass_coverage(self):
  qs=mod.questions('residence')
  j={q['id']:{'status':'ANSWERED_WITH_EVIDENCE','evidence_ids':['INVENTED']} for q in qs}
  a,ready=mod.coverage(qs,[{'evidence_id':'REAL'}],semantic_judgments=j)
  self.assertFalse(ready)
 def test_complete_evidence_ids_remain_draft_only(self):
  qs=mod.questions('residence')
  j={q['id']:{'status':'ANSWERED_WITH_EVIDENCE','evidence_ids':['EV_REAL']} for q in qs}
  a,ready=mod.coverage(qs,[{'evidence_id':'EV_REAL'}],semantic_judgments=j)
  self.assertTrue(ready)
  self.assertFalse(content.plan({'proposals':[{'cluster_id':'residency_options','proposed_title':'Tipos de residencia'}]})['publication_allowed'])
 def test_old_blog_metadata_alone_blocks_new_draft(self):
  p={'proposals':[{'cluster_id':'residency_options','proposed_title':'Tipos de residencia','action':'IMPROVE_EXISTING_ARTICLE'}]}
  self.assertTrue(content.plan(p)['duplicate_metadata'])
 def test_new_article_plan_does_not_read_website(self):
  p={'proposals':[{'cluster_id':'nationality_requirements','proposed_title':'Requisitos para nacionalidad por residencia','action':'create_article'}]}
  self.assertFalse(content.plan(p)['duplicate_metadata'])
 def test_unrecognized_subject_fails_closed(self):
  p={'proposals':[{'cluster_id':'unrelated','proposed_title':'Reclamación de deudas'}]}
  self.assertFalse(content.plan(p)['source_registry_complete'])

if __name__=='__main__':unittest.main()
