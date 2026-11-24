"""Research readiness preserves full missing-fact diagnostics without weakening approval."""
import unittest
from pathlib import Path
from scripts import legal_content_v50, legal_relevance_v50


class ReadinessDiagnosticsTests(unittest.TestCase):
    def test_partial_preserves_reason_and_explicit_missing_facts(self):
        question = {'id': 'steps', 'question': 'Trámite de modificación'}
        evidence = [{'evidence_id': 'EV_REAL'}]
        reason = 'Known evidence does not document the competent filing authority. ' * 12
        judgments = {'steps': {'status': 'PARTIALLY_ANSWERED',
                               'evidence_ids': ['EV_REAL'],
                               'reason': reason,
                               'missing_facts': ['Competent receiving authority not established']}}
        rows, ready = legal_relevance_v50.coverage([question], evidence,
                                                     semantic_judgments=judgments)
        self.assertFalse(ready)
        self.assertEqual(rows[0]['reason'], reason)
        self.assertEqual(rows[0]['missing_facts'], ['Competent receiving authority not established'])

    def test_unknown_id_cannot_mark_question_ready(self):
        rows, ready = legal_relevance_v50.coverage([{'id':'scope'}],
                [{'evidence_id':'EV_REAL'}], semantic_judgments={
                    'scope': {'status':'ANSWERED_WITH_EVIDENCE', 'evidence_ids':['EV_FAKE'],
                              'reason':'Claimed supported'}})
        self.assertFalse(ready)
        self.assertEqual(rows[0]['status'], 'NOT_ANSWERED')

    def test_invalid_missing_facts_shape_is_safe(self):
        rows, ready = legal_relevance_v50.coverage([{'id':'scope'}], [],
            semantic_judgments={'scope': {'status':'PARTIALLY_ANSWERED',
                                           'missing_facts':'not a list'}})
        self.assertEqual(rows[0]['missing_facts'], [])
        self.assertFalse(ready)

    def test_prompt_requests_structured_gaps_without_publishing(self):
        source = Path(legal_content_v50.__file__).read_text(encoding='utf-8')
        self.assertIn('id,status,evidence_ids,reason,missing_facts', source)
        self.assertIn("'publication_allowed':False", source)

if __name__=='__main__':
    unittest.main()
