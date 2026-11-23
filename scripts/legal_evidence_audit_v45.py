"""Claim-to-BOE evidence audit. Explicitly NOT independent legal certification.

A source's exact text, version metadata, and a corroborating reference are
necessary, but cannot alone establish semantic applicability.
"""
import re

def audit_claims(claims,provisions):
    result=[]
    lookup={(p['source_id'],str(p['article'])):p for p in provisions}
    for item in claims:
        p=lookup.get((item.get('source_id'),str(item.get('article',''))))
        record={'claim':item.get('claim',''),'source_id':item.get('source_id'),'article':str(item.get('article','')),'verified_legal_accuracy':False}
        if not p:
            record.update(status='INSUFFICIENT_EVIDENCE',reason='Matching provision not retrieved')
        elif item.get('evidence_excerpt','') not in p.get('text','') or not item.get('evidence_excerpt'):
            record.update(status='INSUFFICIENT_EVIDENCE',reason='Exact evidence quotation not found')
        elif p.get('version_status')=='VERSION_UNCERTAIN':
            record.update(status='NEEDS_INTERPRETATION',reason='Applicable legal version not established')
        else:
            record.update(status='NEEDS_INTERPRETATION',reason='Exact text matched; substantive interpretation and legal applicability still require verification')
        result.append(record)
    return {'claim_audit':result,'publication_allowed':False,'independent_legal_accuracy_verified':False}
