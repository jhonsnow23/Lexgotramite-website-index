import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import legal_content_v46 as v


def fixture(topic='nationality_requirements'):
    return {'version':3,'proposals':[{'cluster_id':'nationality','origin_cluster_id':topic,
        'action':'create_new_article','proposed_title':'Nacionalidad española: requisitos para la solicitud',
        'queries':['requisitos nacionalidad española'],'search_demand_evidence':{'impressions_28d':3}}]}


def fake_retrieve(doc,articles):
    return {'official_url':f'https://www.boe.es/buscar/act.php?id={doc}',
      'provisions':[{'source_id':doc,'article':a,'api_url':f'https://www.boe.es/blocks/{a}',
          'text':f'Artículo {a}. Texto oficial simulado de prueba, que NO debe publicarse y cuyo alcance jurídico queda sin verificar.',
          'version_date':'2026-01-01','version_status':'VERSION_DATE_FOUND_NOT_LEGAL_CERTIFICATION',
          'retrieved_at':'2026-11-23T00:00:00+00:00','legal_status':'UNVERIFIED'} for a in articles]}


def draft_for(evidence):
    return {'title':'Nacionalidad española por residencia: guía de requisitos generales',
      'meta_description':'Guía de preguntas esenciales sobre el procedimiento y sus fuentes oficiales.',
      'introduction':'Esta es una introducción explicativa suficientemente completa para preparar la investigación.',
      'sections':[{'heading':x,'paragraphs':['Este apartado debe documentarse con legislación y procedimientos oficiales pertinentes antes de su publicación.']} for x in ['Requisitos','Procedimiento','Excepciones']],
      'faqs':[], 'claims':[{'claim':'La afirmación de muestra requiere evaluación crítica independiente.',
        'evidence_ids':[evidence[0]['evidence_id']]}], 'unresolved_questions':[]}

class V46Tests(unittest.TestCase):
    def setUp(self):
        self.plan=v.plan(fixture())
        self.evidence,_=v.retrieve_evidence(self.plan,retrieval=fake_retrieve)
    def test_nationality_two_documents(self):
        self.assertEqual(len(self.plan['source_plan']),2)
        self.assertEqual(len(self.evidence),6)
    def test_evidence_id_repeatable(self):
        self.assertEqual(v.stable_id({'source_id':'X','article':'22','text':'a'}),v.stable_id({'source_id':'X','article':'22','text':'a'}))
    def test_no_registry_blocks(self):
        plan=v.plan(fixture('family_reunification'))
        self.assertFalse(plan['source_registry_complete'])
        _,errors=v.retrieve_evidence(plan,retrieval=fake_retrieve)
        self.assertTrue(errors)
    def test_unknown_id_blocks(self):
        article=draft_for(self.evidence); article['claims'][0]['evidence_ids']=['MADE_UP']
        self.assertTrue(any('unknown' in e for e in v.verify_integrity(article,self.evidence,self.plan)))
    def test_unresolved_blocks(self):
        article=draft_for(self.evidence);article['unresolved_questions']=['Which date applies?']
        self.assertIn('Unresolved legal questions',v.verify_integrity(article,self.evidence,self.plan))
    def test_existing_page_blocks_replace(self):
        plan=v.plan(fixture());plan['existing_page_action']='improve_existing_page'
        self.assertTrue(any('reconciled' in e for e in v.verify_integrity(draft_for(self.evidence),self.evidence,plan)))
    def test_missing_sections_blocks(self):
        a=draft_for(self.evidence);a['sections']=[a['sections'][0]]
        self.assertIn('Insufficient substantive sections',v.verify_integrity(a,self.evidence,self.plan))
    def test_wrong_count_review_blocks(self):
        review={'assessment':[],'gaps':[]}
        def client(_):return {'choices':[{'message':{'content':json.dumps(review)}}]}
        _,issues=v.semantic_review(draft_for(self.evidence),self.evidence,client=client)
        self.assertTrue(issues)
    def test_partial_review_blocks(self):
        review={'assessment':[{'claim_index':0,'status':'PARTIALLY_SUPPORTED','reason':'exception'}],'gaps':[]}
        def client(_):return {'choices':[{'message':{'content':json.dumps(review)}}]}
        _,issues=v.semantic_review(draft_for(self.evidence),self.evidence,client=client)
        self.assertIn('Claim 1: PARTIALLY_SUPPORTED',issues)
    def test_html_safe(self):
        a=draft_for(self.evidence);a['title']='<script>alert(1)</script> '+a['title']
        output=v.render(a,self.evidence,{})
        self.assertNotIn('<script>',output)
        self.assertIn('noindex,nofollow',output)
    def test_evidence_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp=Path(tmp)/'p.json';inp.write_text(json.dumps(fixture()))
            def no_source(doc,articles):raise v.BOEError('NETWORK_ERROR','mocked')
            code=v.execute(inp,Path(tmp)/'out',retrieval=no_source)
            self.assertEqual(code,2)
            decision=json.loads((Path(tmp)/'out'/'decision.json').read_text())
            self.assertFalse(decision['publication_allowed'])
    def test_bounded_revision_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp=Path(tmp)/'p.json';inp.write_text(json.dumps(fixture()))
            answer=draft_for(self.evidence)
            calls=[]
            def client(payload):
                calls.append(payload)
                if 'evaluador crítico' in payload['messages'][0]['content']:
                    data={'assessment':[{'claim_index':0,'status':'UNSUPPORTED','reason':'test fixture'}], 'gaps':[]}
                else:data=answer
                return {'choices':[{'message':{'content':json.dumps(data,ensure_ascii=False)}}]}
            code=v.execute(inp,Path(tmp)/'out',retrieval=fake_retrieve,client=client,max_revisions=2)
            self.assertEqual(code,3)
            self.assertEqual(len(calls),6)
            self.assertEqual(json.loads((Path(tmp)/'out'/'decision.json').read_text())['attempts'],3)
            self.assertFalse(json.loads((Path(tmp)/'out'/'decision.json').read_text())['publication_allowed'])
            self.assertTrue((Path(tmp)/'out'/'article.preview.html').exists())

if __name__=='__main__':unittest.main()
