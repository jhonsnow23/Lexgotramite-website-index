"""Run 54 real official extraction + simulated API contract; never live approval."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import first_article_v50 as engine
import evidence_passages_v50 as passages

F=json.loads((Path(__file__).parent/'fixtures/run54_replay.json').read_text(encoding='utf-8'))
E=F['evidence']
ALL=E+[x for records in F['other_archived_records'].values() for x in records]


class ArchivedResearch:
    def __init__(self, ledger):
        self.ledger=ledger
    def article(self, document, article):
        self.ledger.document(f'{document}:{article}')
        rows=[x for x in ALL if x.get('source_id')==document and str(x.get('article'))==str(article)]
        return copy.deepcopy(rows[:1])
    def guidance(self, category, topic):
        if category=='no_lucrativa':
            return copy.deepcopy([x for x in E if x['authority']=='migraciones'])
        if category=='regularizacion_2026':
            return copy.deepcopy([x for x in ALL if x.get('article') in ('DA20.10','DA21.10')])
        return []


def response(value,model):
    return {'id':'simulated_fixture','status':'completed','model':model,
            'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value,ensure_ascii=False)}]}],
            'usage':{'input_tokens':100,'output_tokens':100}}


def proposed(data, *, fixed=True, material=False, request=False):
    p=next(x['passage_id'] for x in data['official_passages'] if x['article']=='64')
    claims=[
        {'section':'Plazo ordinario','text':'Quien quiera renovar su autorización de residencia temporal no lucrativa debe solicitarlo durante los dos meses previos a la fecha de expiración de la autorización.',
         'conditions':'La solicitud se dirige a la oficina de extranjería competente para su tramitación.',
         'exceptions':'El mismo artículo regula también la presentación posterior a la caducidad.', 'passage_ids':[p]},
        {'section':'Efecto de la presentación','text':'La presentación de la solicitud dentro de los dos meses previos prorroga la validez de la autorización anterior hasta la resolución del procedimiento.',
         'conditions':'Se trata de la validez de la autorización anterior mientras se tramita su renovación.',
         'exceptions':'El efecto temporal no equivale por sí mismo a la concesión de la renovación.', 'passage_ids':[p]},
        {'section':'Presentación después de la caducidad','text':'También se prorroga la validez hasta la resolución si la solicitud se presenta dentro de los tres meses posteriores a la expiración de la autorización anterior.',
         'conditions':'Este supuesto se refiere a la renovación de la autorización temporal no lucrativa.',
         'exceptions':'La presentación en ese periodo no impide que se incoe el procedimiento sancionador previsto en el artículo 52.b de la Ley Orgánica 4/2000.' if fixed else 'Debe distinguirse del periodo ordinario anterior a la expiración.', 'passage_ids':[p]}
    ]
    gaps=[{'question':'¿Cumple la persona todos los requisitos individuales?','classification':'APPLICANT_DEPENDENT_CONDITION',
           'reason':'La norma contiene condiciones que deben comprobarse en el caso concreto.', 'passage_ids':[p],
           'reader_limitation':'Esta explicación del plazo no determina si se cumplen los requisitos individuales de renovación.'}]
    if material: gaps.append({'question':'Regla material sin acreditar','classification':'MATERIAL_LEGAL_GAP','reason':'No consta la norma necesaria.', 'passage_ids':[], 'reader_limitation':'No se puede determinar la cuestión.'})
    return {'claims':claims,'gaps':gaps,'additional_articles':[{'document':engine.RD,'article':63,'reason':'Comprobar remisión adicional.'}] if request else []}


def verdict(data, *, approved=True, resolve=True):
    d={'approved':approved,'claim_checks':[{'claim_id':c['claim_id'],'supported':True,'reason':'Simulated check'} for c in data['claims']],
       'prior_defect_checks':[{'defect_id':x['defect_id'],'resolved':resolve,'reason':'Simulated comparison'} for x in data['prior_defects']],
       'defects':[],'explanation':'Simulated reviewer, not legal certification.'}
    d.update({k:True for k in engine.CHECKS})
    if not approved:
        d['no_misleading_omissions']=False
        d['defects']=[{'location':'Presentación después de la caducidad','problem':'Falta advertencia sobre procedimiento sancionador.',
                       'correction':'Incluir la salvedad expresa del artículo 64.1.','additional_articles':[]}]
    return d


class Replay:
    def __init__(self, mode='success'):
        self.mode=mode; self.research_calls=0; self.review_calls=0; self.inputs=[]
    def __call__(self,payload):
        data=json.loads(payload['input']); stage=payload['text']['format']['name']; self.inputs.append((stage,data))
        self.assert_no_secret(payload)
        if stage=='research':
            self.research_calls+=1
            fixed=self.research_calls>1 or self.mode not in ('repair','unresolved_repair','same')
            if self.mode=='same': fixed=False
            raw=proposed(data,fixed=fixed,material=self.mode=='material',request=self.mode=='targeted' and self.research_calls==1)
            if self.mode=='invented': raw['claims'][0]['passage_ids']=['P999999']
            if self.mode=='wrong_route':
                raw['claims'][0]['passage_ids']=[next(x['passage_id'] for x in data['official_passages'] if x['article'] is None)]
        else:
            self.review_calls+=1
            ok=not (self.mode in ('repair','same','unresolved_repair') and self.review_calls==1) and self.mode!='veto'
            raw=verdict(data,approved=ok,resolve=self.mode!='unresolved_repair')
            if self.mode=='contradiction': raw['approved']=False
            if self.mode=='omitted_claim': raw['claim_checks'].pop()
        return response(raw,payload['model'])
    @staticmethod
    def assert_no_secret(payload):
        assert 'api_key' not in payload and payload['store'] is False


class FirstArticleTests(unittest.TestCase):
    def execute(self, mode='success', **kwargs):
        with tempfile.TemporaryDirectory() as t:
            replay=Replay(mode); root=Path(t)
            result=engine.run(root, category='no_lucrativa',transport=replay,researcher_factory=ArchivedResearch,
                limits=kwargs.pop('limits',engine.Limits(research_rounds=3,draft_repairs=2)),**kwargs)
            files={str(p.relative_to(root)):p.read_text(encoding='utf-8') for p in root.rglob('*') if p.is_file()}
            self.assertFalse(result['publication_allowed']); self.assertEqual(result['articles_independently_approved'],0)
            self.assertEqual(result['articles_generated'],0)
            return result,files,replay

    def test_run54_actual_failure_and_candidate_success(self):
        self.assertEqual(F['decision']['result'],'BLOCKED_INSUFFICIENT_EVIDENCE')
        self.assertEqual(sum(len(x['missing_facts']) for x in F['research_coverage']['questions']),8)
        self.assertTrue(all(x['diagnostics']['skip_reason']=='NOT_GENERAL_GUIDANCE' for x in F['gap_assessment_diagnostics']['questions']))
        result,files,replay=self.execute()
        self.assertEqual(result['result'],'SIMULATED_REVIEW_PASS'); self.assertEqual(result['candidate_articles_generated'],1)
        self.assertEqual(replay.review_calls,1)
        prefix='topic_01_no_lucrativa/'
        self.assertIn(prefix+'simulated_article.md',files); self.assertNotIn(prefix+'article.md',files)
        article=json.loads(files[prefix+'candidates/01/candidate.json'])
        self.assertFalse(article['approved']); review=replay.inputs[-1][1]
        self.assertEqual(review['rendered_markdown'],files[prefix+'candidates/01/candidate.md'])
        self.assertEqual(review['article_hash'],article['content_hash'])
        self.assertIn('sancionador',files[prefix+'simulated_article.md'])
        self.assertIn('no determina',files[prefix+'simulated_article.md'])
        catalog=json.loads(files[prefix+'evidence_passage_catalog.json']); evidence=json.loads(files[prefix+'evidence.json'])
        for c in review['claims']:
            for ref in c['passages']: self.assertIsNotNone(passages.resolve_passage(ref['passage_id'],catalog,evidence))

    def test_targeted_retrieval_before_draft(self):
        result,files,replay=self.execute('targeted')
        self.assertEqual(result['result'],'SIMULATED_REVIEW_PASS'); self.assertEqual(replay.research_calls,2)
        self.assertEqual(replay.review_calls,1)
        records=json.loads(files['topic_01_no_lucrativa/evidence.json']); self.assertIn('63',{r['article'] for r in records})

    def test_material_gap_blocks_without_review(self):
        result,_,replay=self.execute('material')
        self.assertEqual(result['result'],'BLOCKED_INSUFFICIENT_EVIDENCE');self.assertEqual(replay.review_calls,0)

    def test_invalid_passage_fails_closed(self):
        result,_,replay=self.execute('invented')
        self.assertEqual(result['result'],'INFRASTRUCTURE_ERROR');self.assertEqual(replay.review_calls,0)

    def test_guidance_only_cannot_prove_legal_claim(self):
        result,_,replay=self.execute('wrong_route',limits=engine.Limits(research_rounds=1,draft_repairs=0))
        self.assertNotEqual(result['result'],'SIMULATED_REVIEW_PASS');self.assertEqual(replay.review_calls,0)

    def test_genuine_veto_remains_binding(self):
        result,files,replay=self.execute('veto',limits=engine.Limits(research_rounds=2,draft_repairs=0))
        self.assertEqual(result['result'],'BLOCKED_LEGAL_VALIDATION');self.assertEqual(replay.review_calls,1)
        self.assertIn('topic_01_no_lucrativa/candidates/01/candidate.md',files)
        self.assertNotIn('topic_01_no_lucrativa/article.md',files)

    def test_actual_draft_is_repaired_and_reviewed(self):
        result,files,replay=self.execute('repair')
        self.assertEqual(result['result'],'SIMULATED_REVIEW_PASS');self.assertEqual(replay.review_calls,2)
        self.assertEqual(result['candidate_articles_generated'],2)
        first=files['topic_01_no_lucrativa/candidates/01/candidate.md']; second=files['topic_01_no_lucrativa/candidates/02/candidate.md']
        self.assertNotIn('sancionador',first);self.assertIn('sancionador',second)
        self.assertTrue(replay.inputs[-1][1]['prior_defects'])

    def test_previous_veto_must_be_resolved(self):
        result,_,replay=self.execute('unresolved_repair',limits=engine.Limits(research_rounds=2,draft_repairs=1))
        self.assertEqual(result['result'],'BLOCKED_LEGAL_VALIDATION');self.assertEqual(replay.review_calls,2)

    def test_unchanged_candidate_is_not_re_reviewed(self):
        result,_,replay=self.execute('same')
        self.assertEqual(result['result'],'BLOCKED_LEGAL_VALIDATION');self.assertEqual(replay.review_calls,1)

    def test_inconsistent_review_never_passes(self):
        result,_,replay=self.execute('contradiction',limits=engine.Limits(research_rounds=1,draft_repairs=0))
        self.assertEqual(result['result'],'BLOCKED_LEGAL_VALIDATION');self.assertEqual(replay.review_calls,1)

    def test_reviewer_must_check_every_claim(self):
        result,_,_=self.execute('omitted_claim',limits=engine.Limits(research_rounds=1,draft_repairs=0))
        self.assertEqual(result['result'],'BLOCKED_LEGAL_VALIDATION')

    def test_api_budget_prevents_call(self):
        result,_,replay=self.execute(limits=engine.Limits(usd=.0001))
        self.assertEqual(result['result'],'BUDGET_EXHAUSTED');self.assertEqual(replay.research_calls,0)

    def test_all_six_categories_and_article_types(self):
        targets=engine.select_topics();self.assertEqual(len(targets),6)
        self.assertEqual(set(engine.PROFILES),{x['category'] for x in targets})
        self.assertTrue(all(not x['search_demand_verified'] for x in targets))
        self.assertEqual(len(engine.TYPES),6)
        with self.assertRaises(ValueError):engine.select_topics(topic='Nacionalidad española')
        with self.assertRaises(ValueError):engine.select_topics(category='arraigo',topic=engine.PROFILES['no_lucrativa'][0])
        for target in targets:
            with self.subTest(target=target['category']):
                with tempfile.TemporaryDirectory() as t:
                    root=Path(t);ledger=engine.Ledger(engine.Limits(),root);r=ArchivedResearch(ledger)
                    cat=target['category']; rows=r.article(engine.RD,engine.PROFILES[cat][1][0])
                    if cat=='menores_no_nacidos':
                        # No archived Article 160: must report missing evidence rather than fabricate it.
                        self.assertEqual(rows,[])
                    else:
                        self.assertTrue(rows)
                        plan=engine.legacy.plan({'proposals':[{'proposed_title':target['topic']}]})
                        catalog,dossier,aliases,context=engine.source_context(rows,plan)
                        self.assertTrue(aliases);self.assertTrue(context);self.assertFalse(dossier['publication_allowed'])

    def test_rotation_when_first_category_cannot_complete(self):
        class Rotate(ArchivedResearch):
            def article(self,document,article):
                if article==64:return []
                return super().article(document,article)
        with tempfile.TemporaryDirectory() as t:
            replay=Replay('success')
            # Second category is reached; replay only knows the first category,
            # so we deliberately stop on one simulated model error, not fake law.
            result=engine.run(t,transport=replay,researcher_factory=Rotate,limits=engine.Limits(topics=2))
            self.assertEqual(len(result['topics_attempted']),2)
            self.assertEqual(result['topics_attempted'][0]['result'],'BLOCKED_INSUFFICIENT_EVIDENCE')
            self.assertFalse(result['publication_allowed'])

    def test_existing_selected_proposal_preserves_demand_metadata(self):
        p={'proposals':[{'proposed_title':engine.PROFILES['no_lucrativa'][0],'cluster_id':'seed_no_lucrativa','action':'create_article','queries':[], 'search_demand_evidence':{'impressions_28d':0}}]}
        x=engine.select_topics(bootstrap=False,proposal=p)[0]
        self.assertFalse(x['search_demand_verified']);self.assertEqual(x['origin'],'SELECTED_PROPOSAL')
        p['proposals'][0]['action']='improve_existing_page'
        with self.assertRaises(ValueError):engine.select_topics(bootstrap=False,proposal=p)

    def test_missing_key_live_mode_has_no_api_calls(self):
        with tempfile.TemporaryDirectory() as t, patch.dict('os.environ',{'OPENAI_API_KEY':''}):
            result=engine.run(t,category='no_lucrativa')
            self.assertEqual(result['result'],'INFRASTRUCTURE_ERROR');self.assertEqual(result['api_calls'],0)
            self.assertEqual(result['articles_generated'],0)

    def test_legacy_publishers_and_new_workflows_are_read_only(self):
        for name in ('lexgo-first-article-v50.yml','lexgo-seo-v50.yml','publish.yml','publish-daily-seo.yml'):
            text=(ROOT/'.github/workflows'/name).read_text()
            # Run 66 explicitly authorizes only the isolated publication job.
            generation=text.split('\n  publish:\n',1)[0] if name=='lexgo-seo-v50.yml' else text
            self.assertIn('contents: read',generation);self.assertNotIn('contents: write',generation)
            if name=='lexgo-seo-v50.yml':
                publication=text.split('\n  publish:\n',1)[1]
                self.assertIn('contents: write',publication);self.assertNotIn('OPENAI_API_KEY',publication)
            self.assertNotIn('git push',text);self.assertNotIn('publish_next_article.py',text)
            if name.startswith('publish'):self.assertNotIn('schedule:',text)


if __name__=='__main__': unittest.main()
