import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('seo_v41',ROOT/'scripts'/'seo_v41.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SOURCE={'id':'BOE-A-2024-24099','url':m.BOE_LEGAL,'fetched_at':'2026-11-23T10:00:00+00:00','sha256':'test',
'extract':'La regulación establece requisitos específicos para los procedimientos mencionados. '*25}
QUOTE='La regulación establece requisitos específicos para los procedimientos mencionados.'
VALID={'title':'Tipos y requisitos de residencia en España: guía detallada', 'meta_description':'Conoce cómo identificar las distintas autorizaciones españolas y consultar los procedimientos oficiales aplicables.',
'introduction':'Esta guía explica las autorizaciones de residencia y cómo verificar sus requisitos. El procedimiento depende de la situación personal.',
'sections':[{'heading':f'Sección {i}', 'paragraphs':['Las condiciones legales deben verificarse en el texto vigente.']*6} for i in range(4)],
'faqs':[{'question':'¿Dónde consultar?','answer':'Consulta el texto oficial.'}],
'claims':[{'claim':'Existen requisitos específicos para procedimientos','source_id':SOURCE['id'],'evidence_excerpt':QUOTE}], 'unresolved_questions':[]}
class Tests(unittest.TestCase):
 def test_extract_multiple_articles(self):
  self.assertEqual(m.extract_article_numbers(['¿Qué indican los artículos 61.2 c) y d), 84 y 89?']),['61','84','89'])
 def test_extract_article_headings_and_seasonal(self):
  raw='\n'.join(['Preámbulo sin contenido clave', 'Artículo 61. Condiciones generales', 'El artículo 61 regula unas condiciones específicas y comprobables.', 'Artículo 84. Temporada', 'Las actividades de temporada tienen disposiciones concretas.', 'Artículo 89. Otros requisitos','Los requisitos se detallan para distintos tipos.'])
  text=m.targeted_evidence(raw,['¿Qué indican los artículos 61, 84 y 89?','¿Qué establece la temporada?'])
  for n in ['61','84','89']: self.assertIn('Artículo '+n,text)
 def test_revision_called_and_revalidated(self):
  pending=dict(VALID,unresolved_questions=['¿Qué establecen los artículos 61, 84 y 89?'])
  raw='\n'.join(['Artículo 61. Condiciones generales','La norma incluye condiciones concretas sobre determinadas autorizaciones.','Artículo 84. Temporada','El procedimiento correspondiente tiene reglas específicas.','Artículo 89. Otras condiciones','Hay condiciones particulares relevantes.'])
  proposals={'proposed_title':'Tipos de residencia','sections_to_research':[]}
  calls=[]
  def revision(p,sources,model):
   calls.append((p,sources))
   self.assertIn('REVISION OF EXISTING ARTICLE',p['sections_to_research'][0])
   return VALID
  updated,audit=m.complete_research(pending,[dict(SOURCE)],{SOURCE['id']:raw},proposals,model='test',generator=revision)
  self.assertEqual(updated['unresolved_questions'],[])
  self.assertEqual(len(calls),1)
  self.assertEqual(audit[0]['attempt'],1)
 def test_no_evidence_stops_without_rewriting(self):
  pending=dict(VALID,unresolved_questions=['¿Qué regula un supuesto desconocido?'])
  updated,audit=m.complete_research(pending,[dict(SOURCE)],{SOURCE['id']:'Sin evidencia adicional relevante'}, {},model='test',generator=lambda *a,**kw:self.fail('Must not call AI without evidence'))
  self.assertEqual(updated['unresolved_questions'],pending['unresolved_questions'])
  self.assertEqual(len(audit),1)
 def test_bounded_two_revisions_and_fail_closed(self):
  pending=dict(VALID,unresolved_questions=['¿Qué dice el artículo 84?'])
  raw='Artículo 84. Reglas temporales\nLa autorización de temporada está regulada por reglas de aplicación particular.'
  calls=[]
  def still_pending(p,sources,model):
   calls.append(1)
   return dict(pending)
  revised,audit=m.complete_research(pending,[dict(SOURCE)],{SOURCE['id']:raw},{},model='test',generator=still_pending)
  self.assertLessEqual(len(calls),2)
  self.assertTrue(revised['unresolved_questions'])
  self.assertIn('Outstanding legal research questions',m.validate_draft(revised,[SOURCE])['errors'])
 def test_publication_forbidden_after_research_success(self):
  draft=dict(VALID)
  self.assertFalse(m.validate_draft(draft,[SOURCE])['publication_allowed'])
 def test_old_v42_contract_unchanged(self):
  text=(ROOT/'.github/workflows/seo-v42-demand-drafts.yml').read_text()
  self.assertIn('python scripts/seo_v41.py --proposals reports/seo_v42/selected_v41_proposal.json',text)

if __name__=='__main__':unittest.main()
