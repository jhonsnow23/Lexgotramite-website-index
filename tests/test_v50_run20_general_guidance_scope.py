"""Run 20: overview-level evidence questions never become a universal checklist."""
import sys
import inspect
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import legal_content_v50 as legal
from temporary_residence_policy_v50 import research_questions

class Run20ScopeTests(unittest.TestCase):
    def test_extraordinary_topic_has_three_constrained_questions(self):
        q=research_questions('regularizacion_2026')
        self.assertEqual([x['id'] for x in q],['scope','requirements','steps'])
        self.assertIn('YA tiene',q[0]['question'])
        self.assertIn('sin inventar una lista universal',q[1]['question'])
        self.assertIn('NO VERIFICADOS',q[2]['question'])

    def test_other_categories_keep_existing_research(self):
        for c in ['arraigo','cuenta_ajena','cuenta_propia','no_lucrativa','menores_no_nacidos']:
            q=research_questions(c)
            self.assertEqual(len(q),3)
            self.assertIn('requisitos, documentos y excepciones',q[1]['question'])

    def test_readiness_does_not_shortcut_review_or_publication(self):
        import inspect
        src=inspect.getsource(legal.research_readiness)
        self.assertIn('PARTIALLY_ANSWERED',src)
        self.assertIn('REQUIRES_LEGAL_INTERPRETATION',src)
        self.assertIn('specific evidence',src)
        self.assertIn('coverage(',src)
        assert 'publicacion' not in src.lower()
        self.assertIn("'publication_allowed':False",inspect.getsource(legal.execute))

    def test_existing_legal_source_filter_unmodified(self):
        src=inspect.getsource(legal.focused_evidence_for_topic)
        self.assertIn("'191','74','80','84','86'",src)
        self.assertIn('NOT_POST_GRANT_CONTINUITY_EVIDENCE',src)

if __name__ == '__main__': unittest.main()
