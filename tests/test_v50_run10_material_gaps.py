"""Run 10: narrow optional gaps without downgrading legal safeguards."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import legal_content_v50 as lc

class Run10Tests(unittest.TestCase):
    def test_prompts_distinguish_optional_from_material(self):
        self.assertIn('mera posibilidad de canales telemáticos',lc.SYSTEM_WRITER)
        self.assertIn('NO es una',lc.SYSTEM_WRITER)
        self.assertIn('No conviertas el silencio',lc.SYSTEM_WRITER)
        self.assertIn('no exijas que',lc.SYSTEM_REVIEW)
        self.assertIn('No apruebes afirmaciones falsas',lc.SYSTEM_REVIEW)

    def test_revision_feedback_is_explicit_and_not_silently_cleared(self):
        prior={'unresolved_questions':['¿Existe un canal alternativo?'],'claims':[]}
        audit={'review':{'gaps':['Un material legal issue']}}
        capture={}
        def fake(messages,**kwargs):
            import json
            capture.update(json.loads(messages[1]['content']))
            return prior
        with patch.object(lc,'call_model',fake):
            result=lc.article_request({'topic':'TIE'},[],previous=prior,findings=audit)
        self.assertIs(result,prior)
        self.assertEqual(capture['revision_requirements']['unresolved_questions_to_resolve_or_justify'],prior['unresolved_questions'])
        self.assertEqual(capture['revision_requirements']['review_gaps'],audit['review']['gaps'])

    def test_unresolved_material_question_still_blocks(self):
        a={'title':'A'*40,'meta_description':'A'*40,'introduction':'A'*60,
           'sections':[{'heading':'H','paragraphs':['A'*70]} for _ in range(3)],
           'claims':[{'claim':'a credible claim','evidence_ids':['E1']}],
           'unresolved_questions':['A concrete, material unresolved legal issue']}
        evidence=[{'evidence_id':'E1','version_status':'CURRENT'}]
        plan={'source_registry_complete':True,'group':'other','topic':'Other'}
        self.assertIn('Unresolved legal questions',lc.verify_integrity(a,evidence,plan))

if __name__=='__main__':unittest.main()
