import importlib
import json
import pathlib
import sys
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from legal_applicability_v50 import (build_dossier, question_matrix, procedure_context,
                                     scope_conflicts, audit_declared_claims, CATEGORIES)
from temporary_residence_policy_v50 import classify, research_questions
import legal_content_v50 as engine


def plan_for(category, topic=None):
    if topic is None:
        from temporary_residence_policy_v50 import SEEDS
        topic = SEEDS[category]['proposed_title']
    c = classify(topic)
    assert c['business_category'] == category and not c['excluded'], c
    return {'topic': topic,'group':'arraigo' if category == 'regularizacion_2026' else 'renewal',
            'commercial_classification':c,'research_questions':research_questions(category),
            'source_registry_complete':True}


def evidence(id, source, article=None, title='', text='', context=False):
    return {'evidence_id':id,'source_id':source,'article':article,
            'document_title':title,'text':text,'authority': 'boe' if source.startswith('BOE-') else source,
            'official_url':'https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8284' if source=='boe' else 'https://www.inclusion.gob.es/',
            'retrieved_at':'2026-11-24T20:00:00+00:00','research_relevance':{'context_only':True} if context else {}}


class LegalApplicabilityTests(unittest.TestCase):
    def test_regularization_not_ordinary_arraigo(self):
        p=plan_for('regularizacion_2026')
        c=procedure_context(p)
        self.assertEqual(c['legal_regime'],'REGULARIZACION_EXTRAORDINARIA_2026')
        self.assertEqual(c['discovery_group_legacy'],'arraigo')
        self.assertEqual(c['editorial_scope'],'GENERAL_GUIDANCE')
        self.assertEqual({r['procedure_type'] for r in c['routes']},{'MODIFICACION','PRORROGA'})

    def test_cross_references_are_context_not_universal_requirements(self):
        p=plan_for('regularizacion_2026')
        rows=[evidence('A','BOE-A-2024-24099','191'),evidence('B','BOE-A-2024-24099','74'),
              evidence('C','BOE-A-2024-24099','80',context=True)]
        d=build_dossier(p,rows)
        self.assertEqual([r['applicability'] for r in d['applicability_evidence']],
                         ['CONDITIONALLY_APPLICABLE','CONTEXT_ONLY','CONTEXT_ONLY'])
        self.assertEqual(d['applicability_evidence'][1]['destination_authorization'],[])
        self.assertFalse(d['legal_accuracy_certified'])
        self.assertFalse(d['publication_allowed'])

    def test_ex26_is_procedural_not_proof_of_eligibility(self):
        p=plan_for('regularizacion_2026')
        d=build_dossier(p,[evidence('EX','migraciones',title='EX-26 Modificación',text='solicitud')])
        self.assertEqual(d['applicability_evidence'][0]['applicability'],'PROCEDURAL_GUIDANCE')
        self.assertEqual(d['applicability_evidence'][0]['verification_status'],'UNVERIFIED_APPLICABILITY')

    def test_unrelated_evidence_does_not_certify_answer(self):
        p=plan_for('regularizacion_2026')
        d=build_dossier(p,[evidence('X','BOE-A-2024-24099','99')])
        q=[{'id':'scope','question':'Opciones','status':'ANSWERED_WITH_EVIDENCE','evidence_ids':['X'],'missing_facts':[]}]
        m=question_matrix(p,[],q,d)
        self.assertIn('EVIDENCE_APPLICABILITY_NOT_ESTABLISHED:X',scope_conflicts(m)[0])

    def test_unknown_id_is_not_substituted(self):
        p=plan_for('regularizacion_2026')
        d=build_dossier(p,[evidence('A','BOE-A-2024-24099','191')])
        m=question_matrix(p,[],[{'id':'scope','status':'ANSWERED_WITH_EVIDENCE','evidence_ids':['FAKE']}],d)
        self.assertTrue(any('UNKNOWN_EVIDENCE_ID:FAKE' in x for x in scope_conflicts(m)))

    def test_partial_stays_partial(self):
        p=plan_for('regularizacion_2026')
        d=build_dossier(p,[evidence('A','BOE-A-2024-24099','191')])
        m=question_matrix(p,[],[{'id':'scope','status':'PARTIALLY_ANSWERED','evidence_ids':['A'],
             'missing_facts':['No se ha acreditado excepción']}],d)
        self.assertEqual(m['questions'][0]['status'],'PARTIALLY_ANSWERED')
        self.assertEqual(len(m['questions'][0]['missing_facts']),1)

    def test_all_six_categories_have_distinct_context(self):
        seen=set()
        for category in CATEGORIES:
            p=plan_for(category)
            d=build_dossier(p,[evidence('E','BOE-A-2024-24099','191')])
            self.assertEqual(d['procedure_context']['business_category'],category)
            seen.add(d['procedure_context']['legal_regime'])
        self.assertEqual(len(seen),6)

    def test_excluded_topics_stay_excluded(self):
        for topic in ('renovación TIE de larga duración','nacionalidad española','cita de huellas'):
            self.assertTrue(classify(topic)['excluded'])

    def test_writer_and_reviewer_receive_dossier(self):
        p=plan_for('regularizacion_2026')
        d=build_dossier(p,[evidence('A','BOE-A-2024-24099','191')])
        captured=[]
        old=engine.call_model
        try:
            def fake(messages, **kwargs):
                captured.append(json.loads(messages[-1]['content']))
                return {'title':'X'}
            engine.call_model=fake
            engine.article_request(p,[],client=lambda _: None,dossier=d)
            self.assertEqual(captured[-1]['legal_applicability_dossier'],d)
        finally:
            engine.call_model=old

    def test_context_only_cannot_solely_support_a_claim(self):
        p=plan_for('regularizacion_2026')
        d=build_dossier(p,[evidence('B','BOE-A-2024-24099','74')])
        result, errors=audit_declared_claims({'claims':[{'claim':'Todos deben renovar conforme al artículo 74','evidence_ids':['B']}]},d)
        self.assertTrue(errors)
        self.assertTrue(result['claims'][0]['context_only_or_unknown'])

    def test_conditional_evidence_still_requires_independent_review(self):
        p=plan_for('regularizacion_2026')
        d=build_dossier(p,[evidence('A','BOE-A-2024-24099','191')])
        result, errors=audit_declared_claims({'claims':[{'claim':'Existe una modificación que debe comprobarse','evidence_ids':['A']}]},d)
        self.assertFalse(errors)
        self.assertTrue(result['claims'][0]['requires_independent_review'])
        self.assertFalse(result['legal_accuracy_certified'])

    def test_run29_fixture_stays_blocked_without_faking_statuses(self):
        fixture=ROOT/'run29/seo_v50/article/research_coverage.json'
        if not fixture.exists():self.skipTest('Run 29 fixture not present')
        c=json.loads(fixture.read_text())
        p=json.loads((ROOT/'run29/seo_v50/article/research_plan.json').read_text())
        rows=json.loads((ROOT/'run29/seo_v50/article/evidence.json').read_text())
        ids=set(json.loads((ROOT/'run29/seo_v50/article/evidence_focus.json').read_text())['selected_evidence_ids'])
        rows=[x for x in rows if x['evidence_id'] in ids]
        d=build_dossier(p,rows)
        matrix=question_matrix(p,rows,c['questions'],d)
        self.assertEqual(len(matrix['questions']),3)
        self.assertTrue(all(q['status']=='PARTIALLY_ANSWERED' for q in matrix['questions']))
        self.assertFalse(d['publication_allowed'])

if __name__=='__main__':unittest.main()
