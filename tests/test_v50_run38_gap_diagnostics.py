import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_v50_run35_branch_applicability import legal

FIXTURE=json.loads((Path(__file__).parent/'fixtures/run37_replay.json').read_text())

class Run38Tests(unittest.TestCase):
    def setUp(self):
        self.plan=FIXTURE['research_plan']; self.rows=FIXTURE['evidence']
        self.dossier=legal.build_dossier(self.plan,self.rows)
        self.branch=legal.general_guidance_branch_coverage(self.rows,self.dossier)
        self.q=FIXTURE['research_coverage']['questions'][1]
        self.assertTrue(self.branch['ready'])
        self.aliases={r['evidence_id']:f'R{i:03d}' for i,r in enumerate(self.rows,1)}
        self.judgment={'questions':[{**q,'evidence_ids':[self.aliases[x] for x in q['evidence_ids']]} for q in FIXTURE['research_coverage']['questions']]}

    def row(self,i,kind='EDITORIAL_EXCLUSION',refs=None):
        refs=refs if refs is not None else ['R001']
        by_ref={**{f'R{n:03d}':r for n,r in enumerate(self.rows,1)},**{r['evidence_id']:r for r in self.rows}}
        return {'index':i,'classification':kind,'reason':'Simulated independent assessment; not a legal finding',
                'retained_answer':'Describe the expressly documented branches only',
                'limitation':'No conclusion on the unresolved route or eligibility for exceptional extension',
                'evidence_ids':refs,'supporting_passages':[{'evidence_id':r,'quote':by_ref[r]['text'][:160]} for r in refs if r in by_ref]}

    def classify(self,*outputs,question=None):
        with patch.object(legal,'call_model',side_effect=outputs) as m:
            r=legal._general_guidance_missing_fact_classification(question or self.q,self.branch,plan=self.plan,evidence=self.rows,dossier=self.dossier,model='gpt-4.1-mini',client=None)
        return r,m

    def test_material_is_recorded_not_approved(self):
        r,_=self.classify({'assessments':[self.row(0,'MATERIAL',[]),self.row(1,'MATERIAL')]})
        self.assertEqual(len(r['blocking_missing_facts']),2)
        self.assertEqual(len(r['gap_assessments']),2)
        self.assertEqual(r['gap_diagnostics']['accepted'][0]['decision'],'BLOCKED')

    def test_independent_valid_row_survives_missing_duplicate_or_invalid_index(self):
        for extra,reason in [([], 'MISSING_INDEX'),([self.row(1),self.row(1)],'DUPLICATE_INDEX'),([self.row(9)],'MISSING_INDEX'),([self.row(1,refs=['R999'])],'INVALID_EVIDENCE_IDS')]:
            with self.subTest(reason=reason):
                r,_=self.classify({'assessments':[self.row(0)]+extra})
                self.assertEqual(r['editorial_exclusions'],[self.q['missing_facts'][0]])
                self.assertEqual(r['blocking_missing_facts'],[self.q['missing_facts'][1]])
                self.assertIn(reason,[x['reason'] for x in r['gap_diagnostics']['rejected']])

    def test_canonical_evidence_ids_are_accepted_only_if_exact(self):
        r,_=self.classify({'assessments':[self.row(0,refs=[self.rows[0]['evidence_id']]),self.row(1,refs=[self.rows[1]['evidence_id']+'x'])]})
        self.assertEqual(r['gap_assessments'][0]['evidence_ids'],[self.rows[0]['evidence_id']])
        self.assertEqual(r['blocking_missing_facts'],[self.q['missing_facts'][1]])

    def test_invented_passage_blocks_only_its_gap(self):
        bad={**self.row(1),'supporting_passages':[{'evidence_id':'R001','quote':'An invented legal paragraph that does not occur in the evidence.'}]}
        r,_=self.classify({'assessments':[self.row(0),bad]})
        self.assertEqual(r['blocking_missing_facts'],[self.q['missing_facts'][1]])
        self.assertEqual(r['gap_diagnostics']['rejected'][0]['reason'],'INVALID_SUPPORTING_PASSAGE')

    def test_invalid_or_empty_response_blocks(self):
        for output in (None,{}, {'assessments':[]}, {'assessments':'bad'}):
            r,_=self.classify(output)
            self.assertEqual(r['blocking_missing_facts'],self.q['missing_facts'])
            self.assertTrue(r['gap_diagnostics']['rejected'])

    def test_parse_error_retries_but_api_error_blocks(self):
        r,m=self.classify(json.JSONDecodeError('bad','x',0),{'assessments':[self.row(0),self.row(1,'MATERIAL')]})
        self.assertEqual(m.call_count,2); self.assertEqual(len(r['blocking_missing_facts']),1)
        r,m=self.classify(RuntimeError('credential error'))
        self.assertEqual(m.call_count,1); self.assertEqual(len(r['blocking_missing_facts']),2)
        self.assertEqual(r['gap_diagnostics']['attempts'][0]['status'],'CALL_ERROR')

    def test_raw_transport_invalid_json_then_valid(self):
        valid={'assessments':[self.row(0),self.row(1,'MATERIAL')]}
        responses=iter(['{broken',json.dumps(valid)])
        def client(payload):
            self.assertEqual(payload['response_format']['type'],'json_schema')
            return {'choices':[{'finish_reason':'stop','message':{'content':next(responses)}}]}
        r=legal._general_guidance_missing_fact_classification(self.q,self.branch,plan=self.plan,evidence=self.rows,dossier=self.dossier,model='gpt-4.1-mini',client=client)
        self.assertEqual(r['gap_diagnostics']['attempts'][0]['raw_response'],'{broken')
        self.assertEqual(r['gap_diagnostics']['attempts'][1]['status'],'PARSED')
        self.assertEqual(r['blocking_missing_facts'],[self.q['missing_facts'][1]])

    def test_skipped_evaluator(self):
        r,m=self.classify(question={**self.q,'missing_facts':[]})
        self.assertFalse(m.called); self.assertEqual(r['gap_diagnostics']['skip_reason'],'NO_GAPS')

    def test_structured_transport_and_redaction(self):
        trace={}; secret='sk-example-secret123456789'
        def client(payload):
            self.assertEqual(payload['response_format']['type'],'json_schema')
            self.assertTrue(payload['response_format']['json_schema']['strict'])
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'assessments':[], 'extra':secret})}}]}
        with patch.dict(os.environ,{'OPENAI_API_KEY':secret}):
            legal.call_model([],client=client,response_format=legal._gap_schema(),diagnostics=trace)
        self.assertNotIn(secret,json.dumps(trace)); self.assertIn('[REDACTED]',trace['raw_response'])

    def replay(self, verdicts, draft=None, review=None):
        responses=[self.judgment,*verdicts]
        if draft is not None: responses.extend([draft,review])
        # The archived evidence is already post-focus/post-split; do not filter it twice.
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); (p/'proposal.json').write_text('{}')
            with patch.object(legal,'plan',return_value=self.plan), patch.object(legal,'retrieve_evidence',return_value=(self.rows,[],{})), patch.object(legal,'focused_evidence_for_topic',side_effect=lambda plan,rows:(rows,[])), patch.object(legal,'call_model',side_effect=responses) as m:
                rc=legal.execute(p/'proposal.json',p/'out',max_revisions=0)
            files={x.name:json.loads(x.read_text()) for x in (p/'out').glob('*.json')}
        return rc,files,m

    def test_real_four_gaps_replay_material_block(self):
        rc,f,m=self.replay([{'assessments':[self.row(0),self.row(1,'MATERIAL')]},{'assessments':[self.row(0,'OPTIONAL_DETAIL'),self.row(1,'MATERIAL')]}])
        self.assertEqual(rc,2); self.assertEqual(m.call_count,3)
        self.assertFalse(f['decision.json']['publication_allowed'])
        self.assertEqual(sum(len(q['blocking_missing_facts']) for q in f['research_coverage.json']['questions']),2)
        self.assertEqual(f['gap_assessment_diagnostics.json']['status'],'EVALUATED')
        self.assertNotIn('article.json',f)

    def test_real_four_gaps_replay_limited_draft_and_independent_veto(self):
        # Synthetic editorial decisions and draft, testing orchestration, not legal accuracy.
        eid=self.rows[0]['evidence_id']; text='El artículo 191 contempla modificaciones de autorizaciones de residencia según el supuesto aplicable.'
        draft={'title':self.plan['topic'],'meta_description':text,'introduction':text,
               'sections':[{'heading':x,'paragraphs':[text]} for x in ('Alcance','Condiciones','Procedimiento')],
               'faqs':[],'claims':[{'claim':text,'evidence_ids':[eid]}],'unresolved_questions':[]}
        verdicts=[{'assessments':[self.row(0),self.row(1,'VERIFIED_BY_MATRIX',['R002','R003'])]},{'assessments':[self.row(0,'OPTIONAL_DETAIL'),self.row(1,'OPTIONAL_DETAIL')]}]
        for verdict,code in [('SUPPORTED',0),('BLOCKED',3)]:
            rc,f,m=self.replay(verdicts,draft,{'assessment':[{'claim_index':0,'status':'SUPPORTED'}],'gaps':[],'scope_limitations_status':verdict})
            self.assertEqual(rc,code, f.get('decision.json')); self.assertEqual(m.call_count,5)
            self.assertTrue(f['research_coverage.json']['ready_for_draft']); self.assertFalse(f['research_coverage.json']['coverage_fully_answered'])
            self.assertFalse(f['decision.json']['publication_allowed'])
            self.assertIn('article.json',f)
            self.assertIn('research_coverage',json.loads(m.call_args.args[0][1]['content']))
