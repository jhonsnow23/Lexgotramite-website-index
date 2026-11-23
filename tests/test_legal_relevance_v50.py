import sys, unittest
from pathlib import Path
import xml.etree.ElementTree as ET
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import legal_relevance_v50 as mod
relevance=mod
import legal_content_v50 as content

class LegalRelevanceTests(unittest.TestCase):
 def test_topic_groups(self):
  self.assertEqual(mod.group_of('residency_options','Tipos de residencia'),'residence')
  self.assertEqual(mod.group_of('nationality_requirements','Nacionalidad española'),'nationality')
  self.assertEqual(mod.group_of('arraigo','Arraigo sociolaboral'),'arraigo')
 def test_excludes_border_crossing(self):
  self.assertEqual(mod.score_title('Artículo 1 Entrada por puestos fronterizos','residencia temporal larga duración'),0)
 def test_relevant_heading(self):
  self.assertGreater(mod.score_title('Residencia de larga duración','tipos residencia temporal larga duración'),0)
 def test_index_block_id_from_official_fields_not_guess(self):
  root=ET.fromstring('<indice><bloque><id>art92x</id><titulo>Art 22 Residencia temporal</titulo></bloque></indice>')
  self.assertEqual(mod.parse_index_titles(root),[('22','art92x','Art 22 Residencia temporal')])
 def test_conflicting_heading_block_mapping_rejected(self):
  root=ET.fromstring('<indice><bloque id="a22" titulo="Art 22"/><bloque id="another22" titulo="Art 22"/></indice>')
  self.assertEqual(mod.parse_index_titles(root),[])
 def test_index_endpoint_matches_working_v45_boe_retriever(self):
  observed=[]
  root=ET.fromstring('<indice><bloque id="a22" titulo="Art 22 Residencia temporal"/></indice>')
  def index_fetch(url):
   observed.append(url)
   return root,'hash'
  mod.discover('residence','Tipos de residencia',index_fetch=index_fetch)
  self.assertEqual(observed, [mod.BASE+'BOE-A-2024-24099/texto/indice'])

 def test_no_positional_fallback(self):
  root=ET.fromstring('<indice><bloque id="art1" titulo="Art 1 Entrada por puestos fronterizos"/><bloque id="art2" titulo="Art 2 Pasaporte"/></indice>')
  results,_=mod.discover('residence','Tipos de residencia',index_fetch=lambda url:(root,'hash'))
  self.assertEqual(results,[])
 def test_unknown_evidence_id_does_not_pass_coverage(self):
  qs=mod.questions('residence')
  j={q['id']:{'status':'ANSWERED_WITH_EVIDENCE','evidence_ids':['INVENTED']} for q in qs}
  a,ready=mod.coverage(qs,[{'evidence_id':'REAL'}],semantic_judgments=j)
  self.assertFalse(ready)
 def test_complete_evidence_ids_remain_draft_only(self):
  qs=mod.questions('residence')
  j={q['id']:{'status':'ANSWERED_WITH_EVIDENCE','evidence_ids':['EV_REAL']} for q in qs}
  a,ready=mod.coverage(qs,[{'evidence_id':'EV_REAL'}],semantic_judgments=j)
  self.assertTrue(ready)
  self.assertFalse(content.plan({'proposals':[{'cluster_id':'residency_options','proposed_title':'Tipos de residencia'}]})['publication_allowed'])
 def test_old_blog_metadata_alone_blocks_new_draft(self):
  p={'proposals':[{'cluster_id':'residency_options','proposed_title':'Tipos de residencia','action':'IMPROVE_EXISTING_ARTICLE'}]}
  self.assertTrue(content.plan(p)['duplicate_metadata'])
 def test_new_article_plan_does_not_read_website(self):
  p={'proposals':[{'cluster_id':'nationality_requirements','proposed_title':'Requisitos para nacionalidad por residencia','action':'create_article'}]}
  self.assertFalse(content.plan(p)['duplicate_metadata'])
 def test_unrecognized_subject_fails_closed(self):
  p={'proposals':[{'cluster_id':'unrelated','proposed_title':'Reclamación de deudas'}]}
  self.assertFalse(content.plan(p)['source_registry_complete'])



DOC="BOE-A-2024-24099"
def fake_index(count=265):
    root=ET.Element('indice')
    for n in range(1,count+1):
        ET.SubElement(root,'bloque',id=f'b{n}',titulo=f'Artículo {n}')
    return root


class FullTextFallbackTests(unittest.TestCase):
    def test_265_generic_article_headings_trigger_distributed_probe(self):
        root=fake_index()
        found,reports=relevance.discover('renewal','renovacion residencia permanente',
             index_fetch=lambda url:(root,'hash'),full_text_probe_limit=48)
        self.assertEqual(len(found),48)
        self.assertEqual(reports[0]['index_articles'],265)
        self.assertEqual(reports[0]['discovery_mode'],'BOUNDED_FULL_TEXT_PROBE')
        self.assertEqual(reports[0]['uninspected_index_articles'],217)
        self.assertEqual(found[0]['article'],'1')
        self.assertEqual(found[-1]['article'],'265')
        self.assertTrue(all(c['discovery_method']=='STRATIFIED_FULL_TEXT_PROBE' for c in found))

    def test_probe_candidate_only_accepted_after_text_validation(self):
        root=fake_index(25)
        calls=[]
        def discovery(group,topic):
            return relevance.discover(group,topic,index_fetch=lambda _: (root,'hash'),full_text_probe_limit=25)
        def retrieval(doc,arts):
            article=str(arts[0]);calls.append(article)
            body=('Artículo '+article+'. La renovación de tarjeta de identidad de extranjero '
                  'acredita la residencia. Requisitos y solicitud del procedimiento de renovación '
                  'de tarjeta de identidad.') if article=='25' else (
                  'Artículo '+article+'. Control de acceso por frontera y puestos fronterizos '
                  'para viajeros y pasaportes.')
            return {'official_url':'https://www.boe.es/buscar/act.php?id='+DOC,
                    'provisions':[{'source_id':DOC,'article':article,'text':body,
                     'api_url':'https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/'+DOC+'/texto/bloque/b'+article,
                     'retrieved_at':'2026-11-23T00:00:00Z','version_status':'VERSION_UNCERTAIN'}]}
        plan={'group':'renewal','topic':'renovacion residencia permanente','research_questions':relevance.questions('renewal')}
        evidence,errors,report=content.retrieve_evidence(plan,retrieval=retrieval,discovery=discovery,return_diagnostics=True)
        self.assertEqual(len(calls),25)
        self.assertEqual([rec['article'] for rec in evidence],['25'])
        self.assertEqual(report['full_text_probes_attempted'],25)
        self.assertEqual(report['accepted_evidence'],1)
        self.assertEqual(len([a for a in report['provision_attempts'] if a['stage']=='REJECTED_FULL_TEXT']),24)
        self.assertEqual(errors,[])

    def test_probe_no_relevant_text_fails_closed(self):
        root=fake_index(12)
        def discovery(group,topic):return relevance.discover(group,topic,index_fetch=lambda _:(root,'hash'))
        def retrieval(doc,arts):
            return {'official_url':'https://www.boe.es/buscar/act.php?id='+DOC,
                    'provisions':[{'source_id':DOC,'article':str(arts[0]),
                      'text':'Artículo '+str(arts[0])+'. Control de pasaportes en frontera para entrada de pasajeros.',
                      'api_url':'https://www.boe.es/api','retrieved_at':'2026-11-23T00:00:00Z'}]}
        evidence,errors,report=content.retrieve_evidence({'group':'renewal','topic':'renovacion residencia permanente',
             'research_questions':relevance.questions('renewal')},retrieval=retrieval,discovery=discovery,return_diagnostics=True)
        self.assertFalse(evidence)
        self.assertEqual(errors[0]['category'],'RELEVANCE_FILTER_REJECTED_ALL')
        self.assertEqual(report['full_text_probes_attempted'],12)



class ObservedBlockReuseTests(unittest.TestCase):
    def test_reused_mapping_rejects_untrusted_block_id(self):
        from boe_universal_v45 import retrieve, BOEError
        with self.assertRaises(BOEError) as ctx:
            retrieve(DOC,['25'],verified_index_mapping={(25,''):'../../untrusted'})
        self.assertEqual(ctx.exception.code,'INVALID_INDEX_MAPPING')

class ReusedIndexNetworkTests(unittest.TestCase):
    def test_valid_reused_block_mapping_skips_index_request(self):
        from unittest.mock import patch
        import boe_universal_v45 as boe
        called=[]
        def fake_api(url, **kwargs):
            called.append(url)
            assert url.endswith('/texto/bloque/b25'),url
            body='Artículo 25. La tarjeta de identidad de extranjero podrá renovarse de acuerdo con el procedimiento y los requisitos de residencia vigentes.'
            return ET.fromstring('<version fecha_vigencia="20250101"><texto>'+body+'</texto></version>'),'sha256'
        with patch.object(boe,'api_get',side_effect=fake_api):
            result=boe.retrieve(DOC,['25'],verified_index_mapping={(25,''):'b25'})
        self.assertEqual(len(called),1)
        self.assertEqual(result['provisions'][0]['article'],'25')
        self.assertEqual(result['provisions'][0]['block_id'],'b25')
        self.assertEqual(result['provisions'][0]['version_status'],'VERSION_DATE_FOUND_NOT_LEGAL_CERTIFICATION')

    def test_reused_mapping_still_rejects_wrong_article(self):
        from unittest.mock import patch
        import boe_universal_v45 as boe
        def fake_api(url,**kwargs):
            return ET.fromstring('<version fecha_vigencia="20250101"><texto>Artículo 1. Entrada por puestos fronterizos y pasaportes para todos los viajeros que lleguen al territorio.</texto></version>'),'sha256'
        with patch.object(boe,'api_get',side_effect=fake_api):
            with self.assertRaises(boe.BOEError) as ctx:
                boe.retrieve(DOC,['25'],verified_index_mapping={(25,''):'b25'})
        self.assertEqual(ctx.exception.code,'WRONG_ARTICLE')

