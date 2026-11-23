import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from legal_evidence_audit_v45 import audit_claims
class Tests(unittest.TestCase):
 def test_matching_quotes_not_certification(self):
  claim={'claim':'Requisitos','source_id':'BOE-A-1234-1','article':'22','evidence_excerpt':'Un derecho exige requisitos'}
  provision={'source_id':'BOE-A-1234-1','article':'22','text':'Un derecho exige requisitos','version_status':'VERSION_DATE_FOUND_NOT_LEGAL_CERTIFICATION'}
  r=audit_claims([claim],[provision]);self.assertEqual(r['claim_audit'][0]['status'],'NEEDS_INTERPRETATION');self.assertFalse(r['publication_allowed'])
 def test_missing_evidence_blocks(self):
  r=audit_claims([{'claim':'test','source_id':'N/A','article':'22'}],[]);self.assertEqual(r['claim_audit'][0]['status'],'INSUFFICIENT_EVIDENCE')
if __name__=='__main__':unittest.main()
