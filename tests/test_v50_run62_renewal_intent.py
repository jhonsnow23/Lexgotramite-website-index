"""Archived live GSC and legal evidence; all new article model calls simulated."""
import json, tempfile, unittest, os
from pathlib import Path
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from test_v50_run58_editorial_seo import engine, ActualResearch, response, verdict, report, row
import seo_v50 as seo
import renewal_intent_v50 as renewal

F=json.loads((Path(__file__).parent/'fixtures/run61_renewal_demand_replay.json').read_text())
ROOT=Path(__file__).resolve().parents[1]

def prepare(root, data=F, fallback=True, website=ROOT):
    p=Path(root); (p/'report.json').write_text(json.dumps(data));(p/'history.json').write_text(json.dumps(F['history']));(p/'catalog.json').write_text('{}')
    args=SimpleNamespace(output=str(p/'selection'),report=str(p/'report.json'),history=str(p/'history.json'),catalog=str(p/'catalog.json'),website_root=str(website),today='2026-11-26',retry_failed=False,require_history=False,allow_editorial_fallback=fallback)
    seo.select(args)
    return p/'selection'


def duration_transport(payload):
    data=json.loads(payload['input']); stage=payload['text']['format']['name']
    if stage=='legal_review':
        assert 'dos años' in data['rendered_markdown'] and 'larga duración-UE' in data['rendered_markdown']
        return response(verdict(data),payload['model'])
    p=next(x['passage_id'] for x in data['official_passages'] if x['article']=='64')
    return response({'claims':[
        {'section':'¿Cuánto dura la residencia después de renovarla?', 'text':'Si Extranjería concede la renovación de tu autorización de residencia temporal no lucrativa, la autorización renovada tendrá una vigencia de dos años.', 'conditions':'Esta duración corresponde a una renovación concedida, no a la mera presentación de una solicitud.', 'exceptions':'La regla tiene una excepción: cuando corresponda obtener una autorización de residencia de larga duración o de larga duración-UE.', 'passage_ids':[p]},
        {'section':'¿Qué debes acreditar durante ese periodo?', 'text':'Para renovar, debes contar con medios económicos suficientes para cubrir tu manutención y residencia, y, en su caso, las de tu familia, durante el periodo que corresponda a la renovación.', 'conditions':'Sin necesidad de desarrollar una actividad laboral o profesional, en los términos del artículo 62.', 'exceptions':'', 'passage_ids':[p,next(x['passage_id'] for x in data['official_passages'] if x['article']=='62')]}],
        'gaps':[{'question':'¿Cumplo los requisitos de renovación?','classification':'APPLICANT_DEPENDENT_CONDITION','reason':'El artículo 64.2 establece condiciones individuales.','reader_limitation':'Esta explicación trata la duración y no determina si cumples todos los requisitos de renovación ni si te corresponde otra autorización.','passage_ids':[p]}], 'additional_articles':[]},payload['model'])

class Run62(unittest.TestCase):
    def test_strict_scope(self):
        for q in ['Requisitos arraigo social Cataluña','Solicitar arraigo social','Residencia no lucrativa por primera vez','Renovar tarjeta de larga duración','Renovación TIE arraigo','Renovar residencia','Cómo solicitar regularización masiva','Renovar residencia de hijos menores','Renovación de residencia no lucrativa y arraigo']:
            with self.subTest(q=q):self.assertTrue(renewal.assess(q)['excluded'])
        for cat,q in renewal.FALLBACKS:
            with self.subTest(q=q):self.assertEqual(renewal.assess(q)['business_category'],cat);self.assertFalse(renewal.assess(q)['excluded'])
        for q in ['Cómo renovar arraigo social','Primera renovación de residencia por cuenta ajena','Qué hacer cuando caduca mi permiso de regularización masiva','Renovar residencia no lucrativa por primera vez']:
            with self.subTest(q=q):self.assertFalse(renewal.assess(q)['excluded'])

    def test_real_archived_gsc_rejects_all_initial_topics(self):
        rows,w,p=seo.choose(F,{},ROOT,[],date(2026,11,26));self.assertEqual(len(rows),33);self.assertIsNone(w);self.assertIsNone(p)
        self.assertTrue(all(x['commercial_classification']['excluded'] for x in rows))
        self.assertEqual(F['generic_renewal_signal']['impressions'],311)

    def test_rank_only_eligible_by_measured_impressions(self):
        data=report([row('requisitos arraigo social',10000),row('renovar arraigo social',10),row('renovación residencia no lucrativa',100),row('renovar residencia cuenta propia',5)])
        with tempfile.TemporaryDirectory() as t:
            _,w,p=seo.choose(data,{},t,[],date(2026,11,26));self.assertEqual(w['primary_query'],'renovación residencia no lucrativa');self.assertTrue(seo.gsc_v50.verified_proposal(p['proposals'][0]))

    def test_fallback_is_explicit_and_never_fabricates_demand(self):
        with patch.dict(os.environ,{'LEXGO_KEYWORD_PLANNER_CSV':''}), tempfile.TemporaryDirectory() as t:
            folder=prepare(t,fallback=False);self.assertFalse((folder/'selected_proposal.json').exists())
            folder=prepare(t,fallback=True);p=json.loads((folder/'selected_proposal.json').read_text())['proposals'][0]
            self.assertEqual(p['topic_origin'],'EDITORIAL_SEED');self.assertIsNone(p['search_demand_evidence']);self.assertFalse(p['search_demand_verified']);self.assertIn('cuánto dura',p['proposed_title'])
            kw=json.loads((folder/'renewal_keyword_report.json').read_text());self.assertEqual(len(kw['categories']),6);self.assertTrue(all(not v['gsc_top_20'] for v in kw['categories'].values()))

    def test_import_estimates_not_gsc_and_out_of_scope_ignored(self):
        raw='keyword,avg_monthly_searches\nrequisitos arraigo social,90000\nrenovación residencia por cuenta propia,900\nrenovación residencia no lucrativa,200\n'
        self.assertEqual(len(renewal.planner_rows(raw)),2)
        with patch.dict(os.environ,{'LEXGO_KEYWORD_PLANNER_CSV':raw}),tempfile.TemporaryDirectory() as t:
            folder=prepare(t,fallback=False);p=json.loads((folder/'selected_proposal.json').read_text())
            target=engine.select_topics(bootstrap=False,proposal=p)[0];self.assertEqual(target['origin'],'KEYWORD_PLANNER_IMPORT');self.assertFalse(target['search_demand_verified']);self.assertIsNone(target['search_demand_evidence']);self.assertEqual(target['keyword_planner_estimate']['avg_monthly_searches'],900)
        with self.assertRaises(ValueError):renewal.planner_rows('keyword,avg_monthly_searches\nrenovar arraigo,10-100\n')

    def test_live_initial_topic_rejected_before_any_call(self):
        with tempfile.TemporaryDirectory() as t:
            x=engine.run(t,topic='Requisitos arraigo social Cataluña',bootstrap=False)
            self.assertIn('RENEWAL_ONLY_SCOPE',x['reason']);self.assertEqual(x['api_calls'],0);self.assertFalse(x['publication_allowed'])

    def test_actual_evidence_candidate_from_selected_fallback(self):
        with patch.dict(os.environ,{'LEXGO_KEYWORD_PLANNER_CSV':''}),tempfile.TemporaryDirectory() as t:
            folder=prepare(t);proposal=json.loads((folder/'selected_proposal.json').read_text());output=Path(t,'article')
            summary=engine.run(output,proposal=proposal,bootstrap=False,article_type='specific_question',transport=duration_transport,researcher_factory=ActualResearch,website_root=ROOT,limits=engine.Limits(topics=1,research_rounds=1,draft_repairs=0))
            self.assertEqual(summary['result'],'SIMULATED_REVIEW_PASS',summary);self.assertEqual(summary['api_calls'],2);self.assertFalse(summary['publication_allowed']);self.assertEqual(summary['articles_independently_approved'],0)
            self.assertIn('dos años',(output/summary['simulated_article']).read_text())

    def test_same_topic_history_across_source_ids(self):
        h=[{'cluster_id':'seed_x','date':'2026-11-25','status':'REVIEW_READY','topic':'Renovación de residencia no lucrativa'}]
        self.assertIsNotNone(seo.topic_blocker({'cluster_id':'gsc_x','proposed_title':'renovacion de residencia no lucrativa'},h,date(2026,11,26)))

if __name__=='__main__':unittest.main()
