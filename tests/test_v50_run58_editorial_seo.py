"""Run57 real successful evidence; all new writing/review tests are simulated."""
import copy,json,tempfile,unittest
from pathlib import Path
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from test_v50_run55_first_article import engine, response, verdict, ArchivedResearch
import editorial_quality_v50 as ed
import gsc_opportunities_v50 as gsc
import seo_v50 as seo
import seo_intelligence as intelligence
F=json.loads((Path(__file__).parent/'fixtures/run57_success_replay.json').read_text())
ROOT=Path(__file__).resolve().parents[1]
PREFIX='topic_01_no_lucrativa/'


def changed_raw():
    raw=copy.deepcopy(F['research_round_01.json'])
    # Authored example, not a new real model response or legal certification.
    raw['claims'][0].update(section='Introducción',text='¿Tu residencia no lucrativa está a punto de caducar? Puedes solicitar la renovación durante los dos meses anteriores al vencimiento o dentro de los tres meses siguientes.',conditions='Presenta la solicitud ante la oficina de extranjería competente.')
    raw['claims'][1].update(section='¿Qué pasa mientras esperas la respuesta?',text='Si presentas la solicitud dentro de cualquiera de esos dos periodos, tu autorización anterior seguirá siendo válida hasta que Extranjería resuelva la renovación.',conditions='',exceptions='Si la presentas después de que caduque, pueden iniciar un procedimiento sancionador: el retraso de hasta tres meses está considerado una infracción leve.')
    raw['claims'][2].update(section='¿Cuánto tiempo tiene Extranjería para responder?',text='Extranjería tiene tres meses desde que presentas la solicitud para resolverla y notificártelo.',conditions='',exceptions='Si transcurre ese plazo sin resolución y notificación, la solicitud se entiende aprobada por silencio administrativo positivo.')
    raw['claims'][3].update(section='¿Y si han pasado más de tres meses desde la caducidad?',text='El artículo 64 no atribuye expresamente en ese apartado la extensión de la validez de tu autorización a las solicitudes presentadas fuera de los periodos indicados.',conditions='',exceptions='Este artículo informativo no detalla las consecuencias de presentar la solicitud fuera de esos plazos.')
    raw['gaps'][0]['reader_limitation']='' # resolved source/version question; the standard disclaimer remains
    return raw


class ActualResearch(ArchivedResearch):
    def article(self, document, article):
        self.ledger.document(f'{document}:{article}')
        return copy.deepcopy([r for r in F['evidence.json'] if r['source_id']==document and r.get('article')==str(article)])
    def guidance(self, category, topic):
        return copy.deepcopy([r for r in F['evidence.json'] if r['authority']=='migraciones'])


def row(q,i=30,c=2,p=11,url='https://lexgotramite.com/residencia-espana.html'):
    return {'keys':[q,url],'impressions':i,'clicks':c,'position':p}


def report(rows28,rows90=None):
    # Simulated GSC transport shape. No real search metrics asserted by tests.
    return {'metadata':{'source':'google_search_console_api','verified_google_data':True,'site':'sc-domain:lexgotramite.com','data_end_date':'2026-11-23'},'windows':{'28':[]},'v50_commercial_query_clusters':gsc.cluster_windows({'28':rows28,'90':rows90 or rows28},intelligence.discard_reason)}


class Run58(unittest.TestCase):
    def test_exact_duplicate_fields_only(self):
        self.assertEqual(ed.join_fields('A.','A.','Excepto B.'),'A. Excepto B.')
        self.assertEqual(ed.join_fields('Se puede solicitar.','No se puede solicitar fuera de plazo.',''),'Se puede solicitar. No se puede solicitar fuera de plazo.')

    def test_observed_anchor_matches_article_and_document(self):
        e=F['evidence.json'][0];self.assertEqual(e['article'],'64')
        html='<a href="#a6-6">Artículo 64</a><div id="a6-6"><h3>Artículo 64.</h3></div>'
        self.assertTrue(ed.html_anchor(e,html).endswith('#a6-6'))
        for bad in (html.replace('Artículo 64','Artículo 62'),html.replace('id="a6-6"','id="else"')):
            self.assertIsNone(ed.html_anchor(e,bad))
        self.assertIsNone(ed.html_anchor({**e,'api_url':e['api_url'].replace(engine.RD,engine.LO)},html))
        self.assertEqual(ed.CitationResolver().resolve(e),e['official_url'])

    def test_archived_real_claims_render_review_repair_safely(self):
        calls=[]
        def transport(payload):
            data=json.loads(payload['input']); stage=payload['text']['format']['name'];calls.append(stage)
            if stage=='research':
                self.assertIn('español natural',payload['instructions']); raw=changed_raw()
            else:
                self.assertIn('sugerencias menores',payload['instructions'])
                self.assertIn('¿Tu residencia no lucrativa',data['rendered_markdown'])
                self.assertIn('infracción leve',data['rendered_markdown'])
                self.assertIn('silencio administrativo positivo',data['rendered_markdown'])
                self.assertIn('contactar con Lex Go Trámite',data['rendered_markdown'])
                self.assertIn('No determina por sí sola',data['rendered_markdown'])
                self.assertNotEqual(data['article_hash'],F['legal_review.json']['article_hash'])
                raw=verdict(data);raw['explanation']='Simulated review; minor editorial suggestion only.'
            return response(raw,payload['model'])
        with tempfile.TemporaryDirectory() as t,tempfile.TemporaryDirectory() as site:
            Path(site,'index.html').write_text('<section id="contacto"></section>')
            out=engine.run(t,category='no_lucrativa',transport=transport,researcher_factory=ActualResearch,website_root=site,limits=engine.Limits(topics=1,research_rounds=1,draft_repairs=0))
            self.assertEqual(out['result'],'SIMULATED_REVIEW_PASS');self.assertEqual(calls,['research','legal_review']);self.assertFalse(out['publication_allowed']);self.assertEqual(out['articles_independently_approved'],0)
            md=Path(t,PREFIX+'simulated_article.md').read_text();self.assertEqual(md.count('dos meses anteriores'),1)
            self.assertIn('Artículo 64 del Reglamento',md);self.assertNotIn('\\.',md)
            meta=json.loads(Path(t,PREFIX+'article_metadata.json').read_text());self.assertIn('meta_description',meta);self.assertEqual(meta['origin'],'EDITORIAL_SEED');self.assertIsNone(meta['search_demand_evidence'])
            self.assertTrue(Path(t,PREFIX+'citation_validation_report.json').exists());self.assertTrue(Path(t,'api_usage.json').exists())
            self.assertLess(out['conservative_budget_debit_usd'],.25)

    def test_empty_reader_limitation_only_for_resolved_gap(self):
        raw=changed_raw(); evidence=F['evidence.json'];plan=engine.legacy.plan({'proposals':[{'proposed_title':engine.PROFILES['no_lucrativa'][0]}]})
        cat,dossier,aliases,_=engine.source_context(evidence,plan)
        claims,gaps=engine.validate_research(raw,aliases,cat,evidence,dossier)
        self.assertEqual(gaps[0]['reader_limitation'],'');self.assertTrue(gaps[0]['passages'])
        raw['gaps'][0]['classification']='MATERIAL_LEGAL_GAP'
        with self.assertRaises(engine.IntegrityError):engine.validate_research(raw,aliases,cat,evidence,dossier)
        self.assertTrue(engine.md_escape('# Fake heading').startswith('\\#'))

    def test_minor_repetition_advisory_no_legal_deletion(self):
        p={'claim_id':'C1','text':'La solicitud se presenta ante la oficina competente.','conditions':'La solicitud se presenta ante la oficina competente.','exceptions':'No cambia el plazo.'}
        p2={**p,'claim_id':'C2'}; article={'sections':[{'paragraphs':[p,p2]}]}
        q=ed.quality(article);self.assertTrue(q['advisory_only']);self.assertTrue(q['repetition_signals']);self.assertEqual(article['sections'][0]['paragraphs'][1],p2)

    def test_query_clusters_separate_procedures_and_qualifiers(self):
        rows=[row('cuándo renovar residencia no lucrativa'),row('plazo renovación residencia no lucrativa'),row('plazo renovación residencia cuenta propia'),row('renovar residencia no lucrativa después de caducar'),row('nacionalidad española',1000),row('cuánto tarda regularización extraordinaria 2026',1000)]
        groups=gsc.cluster_windows({'28':rows})['28'];self.assertEqual(len(groups),3)
        grouped=next(x for x in groups if len(x['queries'])==2);self.assertEqual(grouped['impressions'],60);self.assertEqual(grouped['clicks'],4)
        self.assertEqual(grouped['category'],'no_lucrativa')

    def test_select_verified_measured_demand(self):
        r=report([row('cuándo renovar residencia no lucrativa'),row('plazo renovación residencia no lucrativa'),row('renovar residencia cuenta propia',4)])
        with tempfile.TemporaryDirectory() as t:
            rows,winner,proposal=seo.choose(r,{},t,[],date(2026,11,26));self.assertEqual(winner['commercial_classification']['business_category'],'no_lucrativa')
            p=proposal['proposals'][0];self.assertEqual(p['topic_origin'],'GSC_QUERY_CLUSTER');self.assertEqual(p['search_demand_evidence']['impressions_28d'],60)
            target=engine.select_topics(bootstrap=False,proposal=proposal)[0];self.assertTrue(target['search_demand_verified']);self.assertEqual(len(target['queries']),2)
            self.assertEqual(p['search_demand_evidence']['observed_windows']['28']['queries'][0]['impressions'],30)
            p['search_demand_evidence']['impressions_28d']=999
            self.assertFalse(engine.select_topics(bootstrap=False,proposal=proposal)[0]['search_demand_verified'])

    def test_90_day_only_and_overlapping_windows_not_added(self):
        r=report([], [row('plazo renovación residencia no lucrativa',70)])
        with tempfile.TemporaryDirectory() as t:
            _,winner,_=seo.choose(r,{},t,[],date(2026,11,26));self.assertEqual(winner['impressions_28d'],0);self.assertEqual(winner['impressions_90d'],70)

    def test_existing_slug_recommends_improvement_no_generation(self):
        r=report([row('plazo renovación residencia no lucrativa',40)])
        with tempfile.TemporaryDirectory() as t:
            Path(t,'blog').mkdir(); Path(t,'blog/plazo-renovacion-residencia-no-lucrativa.html').write_text('OLD CONTENT DO NOT READ')
            rows,winner,proposal=seo.choose(r,{},t,[],date(2026,11,26));self.assertIsNone(winner);self.assertIsNone(proposal)
            self.assertEqual(rows[0]['recommended_action'],'RECOMMEND_EXISTING_CONTENT_IMPROVEMENT')

    def test_no_seed_without_explicit_fallback_and_no_fake_metrics(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);report_path=p/'report.json';report_path.write_text(json.dumps(report([])));history=p/'history.json';history.write_text('{"events":[]}')
            catalog=p/'catalog.json';catalog.write_text('{}')
            args=SimpleNamespace(output=str(p/'out'),report=str(report_path),catalog=str(catalog),today='2026-11-26',history=str(history),website_root=t,retry_failed=False,require_history=False,allow_editorial_fallback=False)
            seo.select(args);self.assertFalse((p/'out/selected_proposal.json').exists())
            args.allow_editorial_fallback=True;seo.select(args)
            proposal=json.loads((p/'out/selected_proposal.json').read_text());target=engine.select_topics(bootstrap=False,proposal=proposal)[0]
            self.assertFalse(target['search_demand_verified']);self.assertIsNone(target['search_demand_evidence']);self.assertEqual(target['origin'],'EDITORIAL_SEED')

    def test_offline_report_rejected_and_forged_positive_numbers_not_verified(self):
        r=report([row('plazo renovación residencia no lucrativa')]);r['metadata']['verified_google_data']=False
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):seo.choose(r,{},t,[],date(2026,11,26))
        p={'proposals':[{'proposed_title':engine.PROFILES['no_lucrativa'][0],'action':'create_article','search_demand_evidence':{'impressions_28d':100}}]}
        self.assertFalse(engine.select_topics(bootstrap=False,proposal=p)[0]['search_demand_verified'])

    def test_review_ready_draft_not_repeated_next_day(self):
        item={'cluster_id':'gsc_x'};hist=[{'cluster_id':'gsc_x','date':'2026-11-25','status':'REVIEW_READY'}]
        self.assertIn('draft cooldown',seo.topic_blocker(item,hist,date(2026,11,26),ignore_attempt_backoff=True))

if __name__=='__main__':unittest.main()
