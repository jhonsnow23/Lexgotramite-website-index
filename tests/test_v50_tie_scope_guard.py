"""Scope guard regression tests; no network or legal certification."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
from legal_content_v50 import renewal_scope_warnings, SYSTEM_WRITER, SYSTEM_REVIEW

class LongTermTieScopeTests(unittest.TestCase):
    PLAN={'topic':'Renovación de residencia permanente','group':'renewal'}
    def test_flags_initial_eligibility_as_tie_renewal_requirement(self):
        article={'sections':[{'heading':'Requisitos para renovar la TIE',
            'paragraphs':['Para renovar la tarjeta debe cumplir cinco años de residencia legal y continuada en España.']}]}
        self.assertTrue(renewal_scope_warnings(article,self.PLAN))
    def test_explicit_distinction_not_flagged(self):
        article={'sections':[{'heading':'Requisitos para renovar la TIE',
            'paragraphs':['Los cinco años de residencia legal corresponden a la concesión inicial de la autorización, no a la renovación física.']}]}
        self.assertEqual(renewal_scope_warnings(article,self.PLAN),[])
    def test_unrelated_topic_not_flagged(self):
        article={'sections':[{'heading':'Requisitos',
            'paragraphs':['Se exige cinco años de residencia legal y continuada.']}]}
        self.assertEqual(renewal_scope_warnings(article,{'topic':'Renovación arraigo','group':'renewal'}),[])
    def test_review_checks_narrative_not_only_claims(self):
        self.assertIn('TODO el artículo',SYSTEM_REVIEW)
        self.assertIn('concesión inicial',SYSTEM_WRITER)

if __name__=='__main__':unittest.main()
