"""Updated compatibility contract for v4.5. Replaces old aNN fallback assumptions."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import boe_targeted
from test_boe_universal_v45 import opener
class Tests(unittest.TestCase):
 def test_existing_generator_contract(self):
  r=boe_targeted.retrieve_articles('BOE-A-1889-4763',[21,22,23],opener=opener)
  self.assertEqual([x['article'] for x in r['provisions']],['21','22','23'])
  self.assertIn('evidence_text',r)
 def test_not_legally_certified(self):
  r=boe_targeted.retrieve_articles('BOE-A-1889-4763',[22],opener=opener)
  self.assertEqual(r['provisions'][0]['legal_status'],'UNVERIFIED')
if __name__=='__main__':unittest.main()
