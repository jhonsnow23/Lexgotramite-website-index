"""Run 19: inspect legal cross-references without presuming applicability."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import legal_content_v50 as legal

class Article191CrossReferenceTests(unittest.TestCase):
    def setUp(self):
        self.plan={'commercial_classification':{'business_category':'regularizacion_2026'},
                   'topic':'Continuar residencia tras regularización 2026','group':'arraigo'}
    def test_referenced_articles_are_context_not_auto_approved(self):
        def retrieve(source, articles):
            number=articles[0]
            return {'official_url':'https://www.boe.es/buscar/act.php?id='+source,
                    'provisions':[{'source_id':source,'article':number,'api_url':'https://www.boe.es/',
                      'retrieved_at':'2026-11-24T00:00:00Z','text':'Artículo '+number+' requisitos sujetos a supuesto.'}]}
        rows,warnings,attempts=legal.retrieve_referenced_modification_requirements([],retrieve)
        self.assertEqual([x['article'] for x in rows],['74','80','84','86'])
        self.assertFalse(warnings)
        self.assertTrue(all(x['research_relevance']['context_only'] for x in rows))
        selected,excluded=legal.focused_evidence_for_topic(self.plan,rows)
        self.assertEqual(len(selected),4)
        self.assertFalse(excluded)
        self.assertTrue(all(x['research_relevance']['not_automatically_applicable'] for x in selected))
    def test_failed_optional_reference_is_diagnostic(self):
        def retrieve(source,articles):
            if articles[0]=='80':raise OSError('temporary failure')
            return {'official_url':'https://www.boe.es/',
                    'provisions':[{'source_id':source,'article':articles[0],'api_url':'https://www.boe.es/',
                                   'retrieved_at':'2026-11-24T00:00:00Z','text':'Unverified official text'}]}
        rows,warnings,attempts=legal.retrieve_referenced_modification_requirements([],retrieve)
        self.assertEqual(len(rows),3)
        self.assertEqual(len(warnings),1)
        self.assertEqual(warnings[0]['article'],'80')
        blocking,nonblocking=legal.partition_retrieval_errors(warnings)
        self.assertFalse(blocking)
        self.assertEqual(len(nonblocking),1)
    def test_no_other_procedure_is_modified(self):
        other={'commercial_classification':{'business_category':'no_lucrativa'},'topic':'Renovación residencia no lucrativa','group':'renewal'}
        rows=[{'source_id':'BOE-A-2024-24099','article':'191','evidence_id':'Z'}]
        self.assertEqual(legal.focused_evidence_for_topic(other,rows),(rows,[]))

if __name__=='__main__': unittest.main()
