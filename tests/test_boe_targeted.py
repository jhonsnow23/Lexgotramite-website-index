import importlib.util
from pathlib import Path
import io,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('boe_targeted',ROOT/'scripts'/'boe_targeted.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class Response:
 def __init__(self,url,content):self.url=url;self.content=content;self.headers={}
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self,n):return self.content[:n]
 def geturl(self):return self.url
INDEX=b'<root><bloque><id_bloque>a21</id_bloque><titulo>Articulo 21.</titulo></bloque><bloque><id_bloque>a22</id_bloque><titulo>Articulo 22.</titulo></bloque><bloque><id_bloque>a23</id_bloque><titulo>Articulo 23.</titulo></bloque></root>'
BLOCK=b'<root><version><fecha_publicacion>2020-01-01</fecha_publicacion><texto>Texto anterior con suficientes palabras para pasar la prueba de tamano del texto.</texto></version><version><fecha_publicacion>2025-01-01</fecha_publicacion><texto>Esta es la version mas reciente del articulo, que contiene texto juridico para las pruebas automatizadas de la extraccion por bloques.</texto></version></root>'
def opener(req,timeout):return Response(req.full_url,INDEX if req.full_url.endswith('/indice') else BLOCK)
class TestBOE(unittest.TestCase):
 def test_index(self):
  self.assertEqual(b.block_index(b.ET.fromstring(INDEX)),{21:'a21',22:'a22',23:'a23'})
 def test_bounded_articles(self):
  result=b.retrieve_articles('BOE-A-1889-4763',[21,22,23],opener=opener)
  self.assertEqual(len(result['provisions']),3)
  self.assertIn('Artículo 22.',result['evidence_text'])
  self.assertNotIn('Texto anterior',result['evidence_text'])
  self.assertTrue(result['informative_consolidation'])
 def test_missing_article_fails(self):
  with self.assertRaisesRegex(ValueError,'absent from index'):b.retrieve_articles('BOE-A-1889-4763',[24],opener=opener)
 def test_size_budget_fails_not_truncates(self):
  with self.assertRaisesRegex(ValueError,'context budget'):b.retrieve_articles('BOE-A-1889-4763',[21,22],opener=opener,max_total=60)
 def test_malformed_xml(self):
  def invalid(req,timeout):return Response(req.full_url,b'<broken')
  with self.assertRaisesRegex(ValueError,'Invalid official BOE XML'):b.retrieve_articles('BOE-A-1889-4763',[21],opener=invalid)
 def test_bad_identifier(self):
  with self.assertRaisesRegex(ValueError,'Invalid BOE'):b.retrieve_articles('https://evil.test',[22],opener=opener)
 def test_bad_redirect(self):
  def redirected(req,timeout):return Response('https://example.com/capture',INDEX)
  with self.assertRaisesRegex(ValueError,'redirected'):b.retrieve_articles('BOE-A-1889-4763',[22],opener=redirected)
 def test_dtd_blocked(self):
  def dtd(req,timeout):return Response(req.full_url,b'<!DOCTYPE root><root/>')
  with self.assertRaisesRegex(ValueError,'DTD'):b.retrieve_articles('BOE-A-1889-4763',[22],opener=dtd)
 def test_size_blocked(self):
  def big(req,timeout):return Response(req.full_url,b'x'*(b.MAX_INDEX+1))
  with self.assertRaisesRegex(ValueError,'bounded retrieval limit'):b.retrieve_articles('BOE-A-1889-4763',[22],opener=big)
 def test_versions_must_have_dates(self):
  xml=b'<root><version><texto>Long enough text to be a realistic provision with dozens of words and adequate length.</texto></version></root>'
  with self.assertRaisesRegex(ValueError,'date missing'):b.latest_block_text(b.ET.fromstring(xml))
 def test_prevents_publication(self):
  spec=importlib.util.spec_from_file_location('seo_v41',ROOT/'scripts'/'seo_v41.py')
  m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  self.assertFalse(m.validate_draft({},[])['publication_allowed'])
  self.assertIn(('BOE-A-2015-12047',m.BOE_NATIONALITY_PROC),m.SOURCES['nationality'])
if __name__=='__main__':unittest.main()
