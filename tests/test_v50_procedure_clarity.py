"""Regression coverage for procedure-specific research, no live legal certification."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from legal_content_v50 import plan, SYSTEM_WRITER, SYSTEM_REVIEW, verify_integrity

class ProcedureClarityTests(unittest.TestCase):
    def test_plan_asks_about_physical_card(self):
        p=plan({'proposals':[{'proposed_title':'Renovación de residencia permanente',
                             'origin_cluster_id':'long_term_residence','action':'create_article'}]})
        self.assertEqual(len(p['research_questions']),3)
        self.assertIn('renovación física de TIE',p['research_questions'][0]['question'])
        self.assertIn('canales',p['research_questions'][2]['question'])
    def test_other_topics_keep_generic_questions(self):
        p=plan({'proposals':[{'proposed_title':'Renovación de arraigo social',
                             'origin_cluster_id':'renewals','action':'create_article'}]})
        self.assertNotIn('renovación física de TIE',p['research_questions'][0]['question'])
    def test_writer_and_reviewer_cannot_equate_renewals(self):
        self.assertIn('NO equivale',SYSTEM_WRITER)
        self.assertIn('exclusivamente presencial',SYSTEM_WRITER)
        self.assertIn('trámite exacto',SYSTEM_REVIEW)
    def test_material_questions_still_block(self):
        a={'title':'x'*40,'meta_description':'x'*40,'introduction':'x'*40,
           'sections':[{'heading':'Heading','paragraphs':['x'*70]} for _ in range(3)],
           'claims':[{'claim':'A valid claim exceeding twelve letters', 'evidence_ids':['abc']}],
           'unresolved_questions':['Duda material no resuelta']}
        p={'topic':'Renovación de residencia permanente','group':'renewal',
           'source_registry_complete':True,'existing_page_action':'create_article'}
        e=[{'evidence_id':'abc','version_status':'CURRENT'}]
        self.assertIn('Unresolved legal questions',verify_integrity(a,e,p))

if __name__=='__main__': unittest.main()
