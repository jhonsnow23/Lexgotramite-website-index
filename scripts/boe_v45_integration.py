#!/usr/bin/env python3
"""Read-only live BOE smoke test. No article content, keys, or secrets in logs."""
import json
import sys
from pathlib import Path
from boe_universal_v45 import retrieve,probe,BOEError

TARGETS=[('BOE-A-1889-4763',[21,22,23],'Código Civil, nacionalidad'),('BOE-A-2015-12047',[1,2,3],'Nacionalidad, RD 1004/2015'),('BOE-A-2024-24099',[1,2],'Extranjería, RD 1155/2024')]

def main():
 out=Path('reports/boe_v45');out.mkdir(parents=True,exist_ok=True)
 results=[];failed=False
 for doc,articles,label in TARGETS:
  diag=probe(doc)
  entry={'document':doc,'label':label,'requested_articles':articles,'diagnostic':diag,'publication_allowed':False}
  try:
   evidence=retrieve(doc,articles)
   entry['result']='RETRIEVED_NOT_LEGALLY_VERIFIED'
   entry['retrieved_articles']=[x['article'] for x in evidence['provisions']]
   entry['version_statuses']=[x['version_status'] for x in evidence['provisions']]
   (out/f'{doc}.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')
  except BOEError as e:
   failed=True;entry.update({'result':'FAILED','error_code':e.code,'error':str(e)[:240],'endpoint':e.url})
  results.append(entry)
 (out/'integration_results.json').write_text(json.dumps({'results':results,'publication_allowed':False,'all_sources_retrieved':not failed},ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'results':[(r['document'],r['result']) for r in results],'publication_allowed':False}))
 return 2 if failed else 0

if __name__=='__main__':raise SystemExit(main())
