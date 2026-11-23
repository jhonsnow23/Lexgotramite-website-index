import sys,unittest,xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import boe_universal_v45 as m

class Response:
 def __init__(self,url,content):self.url=url;self.content=content
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self,n):return self.content[:n]
 def geturl(self):return self.url

INDEX=b'''<response><data><indice><parte><bloque><id_bloque>x-001</id_bloque><titulo>Art\xc3\xadculo 21.</titulo></bloque><bloque><id_bloque>x-022</id_bloque><titulo>Art\xc3\xadculo 22.</titulo></bloque><bloque><id_bloque>x-023</id_bloque><titulo>Art\xc3\xadculo 23.</titulo></bloque></parte></indice></data></response>'''

def block(url):
 num={'x-001':21,'x-022':22,'x-023':23}[url.rsplit('/',1)[-1]]
 return f'<response><data><bloque><version fecha_vigencia="20250101"><p>Art\u00edculo {num}. Requisitos de prueba.</p><p>Esta disposici\u00f3n establece un conjunto de condiciones legales descritas en detalle sin extrapolaci\u00f3n.</p></version></bloque></data></response>'.encode()

def opener(req,timeout):
 u=req.full_url
 return Response(u,INDEX if u.endswith('/indice') else block(u))

class Tests(unittest.TestCase):
 def test_index_real_titles(self):self.assertEqual(m.index_map(ET.fromstring(INDEX))[(22,'')],'x-022')
 def test_finds_three_sections_without_assuming_a22(self):
  r=m.retrieve('BOE-A-1889-4763',[21,22,23],opener=opener)
  self.assertEqual([x['block_id'] for x in r['provisions']],['x-001','x-022','x-023'])
  self.assertEqual([x['article'] for x in r['provisions']],['21','22','23'])
 def test_missing_block_never_guessed(self):
  with self.assertRaisesRegex(m.BOEError,'ARTICLE_NOT_IN_INDEX'):m.retrieve('BOE-A-1889-4763',[24],opener=opener)
 def test_mismatch_block_rejected(self):
  def wrong(req,timeout):return Response(req.full_url,INDEX if req.full_url.endswith('/indice') else block(req.full_url).replace(b'culo 22',b'culo 99'))
  with self.assertRaisesRegex(m.BOEError,'WRONG_ARTICLE'):m.retrieve('BOE-A-1889-4763',[22],opener=wrong)
 def test_namespace(self):
  xml=b'<r xmlns="urn:boe"><bloque><id_bloque>b71</id_bloque><titulo>Art\xc3\xadculo 71.</titulo></bloque></r>'
  self.assertEqual(m.index_map(ET.fromstring(xml))[(71,'')],'b71')
 def test_ambiguous_index(self):
  xml=b'<r><bloque id="a1" titulo="Articulo 1"/><bloque id="b1" titulo="Articulo 1"/></r>'
  with self.assertRaisesRegex(m.BOEError,'AMBIGUOUS_INDEX'):m.index_map(ET.fromstring(xml))
 def test_versions(self):
  old='<r><version fecha_vigencia="20160101"><p>Art\u00edculo 22. Texto anterior con informaci\u00f3n suficientemente larga.</p></version><version fecha_vigencia="20250101"><p>Art\u00edculo 22. Texto actual con informaci\u00f3n suficientemente larga.</p></version></r>'
  v,d,s=m.version_choice(ET.fromstring(old),as_of=m.dt.date(2026,1,1));self.assertEqual(d,'2025-01-01')
 def test_version_missing_dates_remains_uncertain(self):
  x=ET.fromstring('<r><version/><version fecha_vigencia="20250101"/></r>')
  with self.assertRaisesRegex(m.BOEError,'VERSION_UNCERTAIN'):m.version_choice(x)
 def test_no_clipped_article(self):
  with self.assertRaisesRegex(m.BOEError,'CONTEXT_LIMIT'):m.retrieve('BOE-A-1889-4763',[22],opener=opener,max_context=10)
 def test_redirect_rejected(self):
  def bad(req,timeout):return Response('https://other.example/steal',INDEX)
  with self.assertRaisesRegex(m.BOEError,'UNSAFE_REDIRECT'):m.retrieve('BOE-A-1889-4763',[22],opener=bad)
 def test_probe_useful_diagnostics(self):
  d=m.probe('BOE-A-1889-4763',opener=opener);self.assertEqual(d['diagnosis'],'OK');self.assertEqual(d['recognized_article_count'],3)
 def test_status_stays_unverified(self):
  r=m.retrieve('BOE-A-1889-4763',[22],opener=opener);self.assertEqual(r['provisions'][0]['legal_status'],'UNVERIFIED')

if __name__=='__main__':unittest.main()

class CivilCodeRegressionTests(unittest.TestCase):
 def test_spelled_article_headings(self):
  for label,expected in [('Artículo veintiuno.',21),('Art. veintidós.',22),('Artículo veintitrés.',23)]:
   self.assertEqual(m._number_of(label),(expected,''))
 def test_real_index_ids_with_nonstandard_titles(self):
  xml=b'<response><data><bloque><id>a21</id><titulo>Veintiuno.</titulo></bloque><bloque><id>a22</id><titulo>Veintidos.</titulo></bloque><bloque><id>a23</id><titulo>Veintitres.</titulo></bloque></data></response>'
  mp=m.index_map(ET.fromstring(xml))
  self.assertEqual([mp[(x,'')] for x in (21,22,23)],['a21','a22','a23'])
 def test_index_candidates_must_be_verified_against_retrieved_heading(self):
  idx=b'<response><data><bloque><id>a21</id><titulo>Veintiuno.</titulo></bloque></data></response>'
  def own(req,timeout):
   payload=idx if req.full_url.endswith('/indice') else b'<response><data><bloque><version fecha_vigencia="20250101"><p>Art\xc3\xadculo veintiuno. Condiciones oficiales de nacionalidad acreditadas por esta disposici\xc3\xb3n.</p><p>La parte restante del art\xc3\xadculo contiene los detalles pertinentes de su contenido.</p></version></bloque></data></response>'
   return Response(req.full_url,payload)
  result=m.retrieve('BOE-A-1889-4763',[21],opener=own)
  self.assertEqual(result['provisions'][0]['article'],'21')
  self.assertEqual(result['provisions'][0]['legal_status'],'UNVERIFIED')
 def test_wrong_block_with_real_index_id_rejected(self):
  idx=b'<response><data><bloque><id>a22</id><titulo>Veintidos.</titulo></bloque></data></response>'
  def own(req,timeout):
   payload=idx if req.full_url.endswith('/indice') else b'<response><data><bloque><version fecha_vigencia="20250101"><p>Art\xc3\xadculo 23. Esta referencia es incorrecta pero tiene longitud suficiente para validar.</p></version></bloque></data></response>'
   return Response(req.full_url,payload)
  with self.assertRaisesRegex(m.BOEError,'WRONG_ARTICLE'):
   m.retrieve('BOE-A-1889-4763',[22],opener=own)
 def test_nonexistent_block_never_invented(self):
  idx=b'<response><data><bloque><id>a21</id><titulo>Veintiuno.</titulo></bloque></data></response>'
  def own(req,timeout):return Response(req.full_url,idx)
  with self.assertRaisesRegex(m.BOEError,'ARTICLE_NOT_IN_INDEX'):
   m.retrieve('BOE-A-1889-4763',[22],opener=own)
