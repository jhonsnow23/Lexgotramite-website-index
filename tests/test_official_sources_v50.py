import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import official_sources_v50 as mod

class OfficialSourcesTests(unittest.TestCase):
 def test_selects_residence_card_guidance(self):
  sources=mod.candidates('Renovación de residencia permanente','renewal')
  self.assertEqual({x[0] for x in sources},{'migraciones','policia','administraciones'})
  self.assertTrue(all(mod.allowed(x[2]) for x in sources))
 def test_no_unverified_sources_for_unknown_subject(self):
  self.assertEqual(mod.candidates('Consulta sin correspondencia','other'),[])
 def test_allowlist_and_redirect_restriction(self):
  for url in ['https://www.inclusion.gob.es.evil.org/a','http://www.inclusion.gob.es/a',
    'https://evil.org/','https://sede.policia.gob.es@evil.org/']:
   self.assertFalse(mod.allowed(url))
  self.assertTrue(mod.allowed('https://sede.policia.gob.es/portalCiudadano/'))
  with self.assertRaises(ValueError):
   mod.SafeRedirect().redirect_request(None,None,302,'','', 'https://evil.org/')
 def test_html_evidence_only_from_official_page_and_date_not_certified(self):
  url=mod.SOURCES['long_term_national'][0][2]
  html='<html><head><title>Hoja 49</title><script>DROP TABLE blogs</script></head><body>'+('<p>Documento oficial de residencia de larga duración nacional, tarjeta de identidad.</p>'*5)+'</body></html>'
  record=mod.retrieve_one('migraciones','Hoja 49',url,fetch=lambda _:html)
  self.assertNotIn('DROP TABLE',record['text'])
  self.assertEqual(record['version_status'],'GUIDANCE_DATE_NOT_VERIFIED')
  self.assertEqual(record['legal_status'],'PROCEDURAL_GUIDANCE_UNVERIFIED')
 def test_failure_not_silent(self):
  def offline(_):raise OSError('offline')
  evidence,errors,attempts=mod.retrieve_for_topic('Renovacion residencia permanente','renewal',fetch=offline)
  self.assertFalse(evidence)
  self.assertEqual(len(errors),3)
  self.assertTrue(all(x['status']=='ERROR' for x in attempts))
 def test_excluded_blogs(self):
  self.assertFalse(any('/blog/' in url for collection in mod.SOURCES.values() for _,_,url in collection))

if __name__=='__main__': unittest.main()
