"""Run 35: Article 191 branch mapping and general-guide readiness tests."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from legal_applicability_v50 import (
    build_dossier, general_guidance_branch_coverage, _role,
)
from legal_claim_graph_v50 import build_source_claims
import legal_content_v50 as legal

RD1155 = 'BOE-A-2024-24099'
RD316 = 'BOE-A-2026-8284'

ARTICLE_191_TEXT = '''Artículo 191. De la autorización de residencia temporal a autorización de residencia y trabajo.
1. Las personas extranjeras que se encuentren en España en situación de residencia temporal podrán solicitar otra autorización de residencia temporal y trabajo y acceder a ella, sin necesidad de visado, si cumplen los requisitos exigidos para la autorización solicitada con las especialidades que se establecen en los apartados siguientes.
2. Cuando la persona extranjera que solicita una autorización de residencia y trabajo por cuenta ajena no lleve residiendo al menos un año como titular de una autorización de residencia deberá acreditar el cumplimiento de todos los requisitos establecidos en el artículo 74. La autorización tendrá una vigencia de un año y tendrá consideración de autorización de residencia y trabajo inicial.
3. Cuando la persona extranjera lleva en España al menos un año en situación de residencia y la autorización que se pretende modificar ya habilitaba a trabajar por cuenta ajena o propia, se deberán acreditar los requisitos previstos en el artículo 80 o, en su caso, con los requisitos previstos en el artículo 86. En este caso, la vigencia de la nueva autorización tendrá una duración de cuatro años.
4. Cuando la persona extranjera lleva en España al menos un año en situación de residencia y la autorización que se pretende modificar no habilitaba a trabajar se deberá cumplir con los requisitos establecidos en el artículo 74 excepto el apartado 1.a) y en su caso, el artículo 84.'''

DA20_TEXT = '''La autorización concedida tendrá una vigencia de un año y tendrá la consideración de autorización de residencia temporal por circunstancias excepcionales por razón de arraigo social. Asimismo, habilitará a sus titulares a residir y trabajar por cuenta ajena y por cuenta propia, en cualquier parte del territorio español, ocupación o sector de actividad. Durante los dos meses previos a la fecha de expiración de la vigencia de su autorización de residencia, los titulares podrán solicitar una modificación conforme al artículo 191 de este reglamento. La presentación de la solicitud prorrogará la validez de la autorización anterior hasta la resolución del procedimiento. También se prorrogará hasta la resolución del procedimiento en el supuesto en que la solicitud se presentase dentro de los tres meses posteriores a la fecha en que hubiera finalizado la vigencia de la anterior autorización. Excepcionalmente, si no se pudiera solicitar una modificación conforme a este reglamento, esta autorización podrá ser prorrogada siempre y cuando se acredite estar en búsqueda activa de empleo y debidamente inscrito en el servicio público de empleo o se aporte un informe de esfuerzo de integración emitido por los órganos competentes de la Comunidad Autónoma de su lugar de residencia que recomienden la prórroga. Esta prórroga tendrá una vigencia de un año. No obstante, se podrá prorrogar sin necesidad de acreditar los anteriores requisitos si concurren circunstancias que impidan el acceso al empleo por razones debidamente justificadas, tales como enfermedad grave o discapacidad de la persona solicitante, de su cónyuge o descendiente de primer grado menor de edad o mayores de edad que no sean objetivamente capaces de proveer sus propias necesidades debido a su estado de salud, así como en el supuesto de haber alcanzado la edad legal de jubilación. En estos casos, la prórroga tendrá una duración de cuatro años.'''
DA21_TEXT = DA20_TEXT.replace('arraigo social', 'arraigo extraordinario')


def evidence_fixture():
    rows = [
        {'evidence_id': 'EV_191', 'source_id': RD1155, 'article': '191', 'authority': 'boe',
         'official_url': 'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099',
         'document_title': 'RD 1155/2024 artículo 191', 'text': ARTICLE_191_TEXT},
        {'evidence_id': 'EV_74', 'source_id': RD1155, 'article': '74', 'authority': 'boe',
         'official_url': 'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099',
         'document_title': 'RD 1155/2024 artículo 74', 'text': 'Artículo 74. Requisitos. Para la concesión de una autorización inicial de residencia temporal y trabajo por cuenta ajena será necesario cumplir los siguientes requisitos específicos. Contrato de trabajo firmado y condiciones laborales aplicables.',
         'research_relevance': {'context_only': True}},
        {'evidence_id': 'EV_80', 'source_id': RD1155, 'article': '80', 'authority': 'boe',
         'official_url': 'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099',
         'document_title': 'RD 1155/2024 artículo 80', 'text': 'Artículo 80. Renovación de las autorizaciones de residencia temporal y trabajo por cuenta ajena. Los requisitos se aplican según las condiciones y excepciones expresamente previstas en el reglamento.',
         'research_relevance': {'context_only': True}},
        {'evidence_id': 'EV_84', 'source_id': RD1155, 'article': '84', 'authority': 'boe',
         'official_url': 'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099',
         'document_title': 'RD 1155/2024 artículo 84', 'text': 'Artículo 84. Requisitos de autorización inicial de residencia temporal y trabajo por cuenta propia.',
         'research_relevance': {'context_only': True}},
        {'evidence_id': 'EV_86', 'source_id': RD1155, 'article': '86', 'authority': 'boe',
         'official_url': 'https://www.boe.es/buscar/act.php?id=BOE-A-2024-24099',
         'document_title': 'RD 1155/2024 artículo 86', 'text': 'Artículo 86. Renovación de la autorización de residencia y trabajo por cuenta propia. Los requisitos se aplican según las condiciones y excepciones expresamente previstas en el reglamento.',
         'research_relevance': {'context_only': True}},
        {'evidence_id': 'EV_DA20', 'source_id': RD316, 'article': 'DA20.10', 'authority': 'boe',
         'official_url': 'https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8284',
         'document_title': 'RD 316/2026 DA20.10', 'text': DA20_TEXT},
        {'evidence_id': 'EV_DA21', 'source_id': RD316, 'article': 'DA21.10', 'authority': 'boe',
         'official_url': 'https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8284',
         'document_title': 'RD 316/2026 DA21.10', 'text': DA21_TEXT},
        {'evidence_id': 'EV_EX26', 'source_id': 'migraciones', 'article': None, 'authority': 'migraciones',
         'official_url': 'https://inclusion.gob.es/ex26', 'document_title': 'Formulario EX-26 — modificación de residencia',
         'text': 'EX-26. Solicitud de modificación de autorización de residencia o estancia.'},
    ]
    plan = {'topic': 'Cómo continuar la residencia tras la regularización extraordinaria de 2026',
            'group': 'arraigo',
            'commercial_classification': {'business_category': 'regularizacion_2026', 'excluded': False,
                                          'procedure_type': None}}
    return rows, plan


class Run35BranchTests(unittest.TestCase):
    def test_origin_authorisations_are_separate_and_both_enable_work(self):
        rows, plan = evidence_fixture()
        dossier = build_dossier(plan, rows)
        context = dossier['procedure_context']
        self.assertEqual({x['origin_authorization_id'] for x in context['origin_authorizations']},
                         {'DA20_ARRAIGO_SOCIAL', 'DA21_ARRAIGO_EXTRAORDINARIO'})
        self.assertEqual(context['origin_work_authorized_modalities'], ['CUENTA_AJENA', 'CUENTA_PROPIA'])

    def test_articles_74_80_86_are_branch_specific_despite_context_hint(self):
        rows, plan = evidence_fixture()
        dossier = build_dossier(plan, rows)
        by_id = {x['evidence_id']: x for x in dossier['applicability_evidence']}
        self.assertEqual(by_id['EV_74']['applicability'], 'CONDITIONALLY_APPLICABLE')
        self.assertEqual(by_id['EV_74']['destination_authorization'], ['MOD_ART191_2_AJENA_LT_1Y'])
        self.assertEqual(by_id['EV_80']['destination_authorization'], ['MOD_ART191_3_AJENA_GE_1Y'])
        self.assertEqual(by_id['EV_86']['destination_authorization'], ['MOD_ART191_3_PROPIA_GE_1Y'])
        self.assertEqual(by_id['EV_84']['applicability'], 'CONTEXT_ONLY')
        self.assertEqual(by_id['EV_84']['destination_authorization'], [])

    def test_general_guide_has_branch_coverage_and_explicit_unresolved_own_account_lt_1y(self):
        rows, plan = evidence_fixture()
        dossier = build_dossier(plan, rows)
        coverage = general_guidance_branch_coverage(rows, dossier)
        self.assertTrue(coverage['applicable'])
        self.assertTrue(coverage['ready'], coverage['missing'])
        self.assertTrue(any('cuenta propia antes de cumplir un año' in x
                            for x in coverage['unresolved_legal_branches']))

    def test_individual_facts_and_unverified_channel_are_nonblocking_only_for_general_guide(self):
        rows, plan = evidence_fixture()
        dossier = build_dossier(plan, rows)
        questions = [
            {'id': 'scope', 'question': 'scope', 'status': 'PARTIALLY_ANSWERED',
             'evidence_ids': ['R001', 'R006', 'R007'],
             'missing_facts': ['Specific individual eligibility criteria for each modification modality under Article 191',
                               'Exact conditions triggering the exceptional prórroga and its applicability to the extraordinary 2026 authorization holders']},
            {'id': 'requirements', 'question': 'requirements', 'status': 'PARTIALLY_ANSWERED',
             'evidence_ids': ['R001', 'R002', 'R003', 'R005', 'R006', 'R007'],
             'missing_facts': ["Individual applicant’s prior authorization type and residence duration to determine applicable Article 191 modality",
                               'Verification of whether the exceptional prórroga conditions (active job search, integration report, or justified impediments) apply to the applicant']},
            {'id': 'steps', 'question': 'steps', 'status': 'PARTIALLY_ANSWERED',
             'evidence_ids': ['R006', 'R007', 'R008'],
             'missing_facts': ['Complete list of required documents for modification or prórroga specific to the extraordinary 2026 authorization holders',
                               'Official channels or exclusive procedures for filing modification or prórroga requests beyond the EX-26 form']},
        ]
        model_result = {'questions': questions}
        with patch.object(legal, 'call_model', return_value=model_result):
            covered, ready = legal.research_readiness(plan | {'research_questions': [
                {'id': 'scope', 'question': 'scope'}, {'id': 'requirements', 'question': 'requirements'},
                {'id': 'steps', 'question': 'steps'}]}, rows, dossier=dossier)
        self.assertTrue(ready)
        self.assertTrue(all(q['draft_readiness'] == 'READY_WITH_DECLARED_LIMITATIONS' for q in covered))
        self.assertTrue(covered[0]['resolved_by_official_branch_matrix'])
        self.assertTrue(covered[1]['individual_case_variables'])
        self.assertTrue(covered[2]['non_blocking_unverified_details'])
        self.assertTrue(all(q['status'] == 'PARTIALLY_ANSWERED' for q in covered))

    def test_unverified_material_legal_rule_still_blocks_general_guide(self):
        rows, plan = evidence_fixture()
        dossier = build_dossier(plan, rows)
        questions = [
            {'id': 'scope', 'question': 'scope', 'status': 'PARTIALLY_ANSWERED',
             'evidence_ids': ['R001', 'R006', 'R007'],
             'missing_facts': ['The legal rule governing an additional route is not established by the supplied official provisions']},
            {'id': 'requirements', 'question': 'requirements', 'status': 'ANSWERED_WITH_EVIDENCE',
             'evidence_ids': ['R001', 'R002', 'R003', 'R005', 'R006', 'R007'], 'missing_facts': []},
            {'id': 'steps', 'question': 'steps', 'status': 'ANSWERED_WITH_EVIDENCE',
             'evidence_ids': ['R006', 'R007', 'R008'], 'missing_facts': []},
        ]
        with patch.object(legal, 'call_model', return_value={'questions': questions}):
            covered, ready = legal.research_readiness(plan | {'research_questions': [
                {'id': 'scope', 'question': 'scope'}, {'id': 'requirements', 'question': 'requirements'},
                {'id': 'steps', 'question': 'steps'}]}, rows, dossier=dossier)
        self.assertFalse(ready)
        self.assertEqual(covered[0]['draft_readiness'], 'BLOCKED')
        self.assertTrue(covered[0]['blocking_missing_facts'])

    def test_graph_attaches_article_74_80_86_to_correct_branch(self):
        rows, plan = evidence_fixture()
        dossier = build_dossier(plan, rows)
        questions = [{'id': 'requirements', 'evidence_ids': [r['evidence_id'] for r in rows]}]
        graph = build_source_claims(rows, dossier, questions)
        by_article = {}
        for claim in graph['source_claims']:
            eid = claim['source_passage']['evidence_id']
            row = next(x for x in rows if x['evidence_id'] == eid)
            by_article.setdefault(str(row.get('article')), set()).update(claim['procedure_routes'])
        self.assertIn('MOD_ART191_2_AJENA_LT_1Y', by_article.get('74', set()))
        self.assertIn('MOD_ART191_3_AJENA_GE_1Y', by_article.get('80', set()))
        self.assertIn('MOD_ART191_3_PROPIA_GE_1Y', by_article.get('86', set()))
        self.assertNotIn('84', by_article)


    def test_missing_branch_source_keeps_general_guide_blocked(self):
        rows, plan = evidence_fixture()
        rows = [row for row in rows if row.get('article') != '86']
        dossier = build_dossier(plan, rows)
        coverage = general_guidance_branch_coverage(rows, dossier)
        self.assertFalse(coverage['ready'])
        self.assertTrue(any('BOE-A-2024-24099:86' in item for item in coverage['missing']))

    def test_article_writer_receives_nonblocking_coverage_limitations(self):
        rows, plan = evidence_fixture()
        report = [{'id': 'steps', 'status': 'PARTIALLY_ANSWERED',
                   'draft_readiness': 'READY_WITH_DECLARED_LIMITATIONS',
                   'non_blocking_unverified_details': ['Exclusive filing channel not verified']}]
        with patch.object(legal, 'call_model', return_value={'title': 'draft'}) as mocked:
            legal.article_request(plan, rows, client=None, dossier=build_dossier(plan, rows),
                                  research_coverage=report)
        payload = json.loads(mocked.call_args.args[0][1]['content'])
        self.assertEqual(payload['research_coverage'], report)

    def test_article_191_sentence_maps_both_80_and_86_branches(self):
        rows, plan = evidence_fixture()
        dossier = build_dossier(plan, rows)
        graph = build_source_claims(rows, dossier, [{'id': 'requirements', 'evidence_ids': ['EV_191']}])
        routes = {r for c in graph['source_claims'] for r in c['procedure_routes']}
        self.assertIn('MOD_ART191_3_AJENA_GE_1Y', routes)
        self.assertIn('MOD_ART191_3_PROPIA_GE_1Y', routes)


if __name__ == '__main__':
    unittest.main()
