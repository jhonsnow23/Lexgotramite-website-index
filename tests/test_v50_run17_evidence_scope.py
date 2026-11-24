"""Run 17: select actual continuation answers and exclude unrelated legal rules."""
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import official_sources_v50 as official
import legal_content_v50 as legal

class Run17Continuity(unittest.TestCase):
    def test_prefers_answer_over_table_of_contents(self):
        heading = '39 . ¿ Qué pasa con la autorización después del primer año ?\n'
        toc = 'ÍNDICE\n' + heading + '40 . ¿ Se puede renovar ?\n' + 'Introducción. ' * 1600 + '\n'
        answers = (heading + 'Dentro de los dos meses anteriores debe solicitar una modificación conforme al artículo 191, cuando proceda.\n'
                   '40 . ¿ Se puede renovar directamente ?\n'
                   'La continuidad debe estudiarse mediante modificación o prórroga, no renovación ordinaria.\n'
                   '41 . ¿ Qué duración tiene ?\n'
                   'La respuesta depende del régimen y del cumplimiento de requisitos.\n')
        extract = official.excerpt_for_procedure_guidance(toc + answers)
        self.assertIn('Dentro de los dos meses anteriores', extract)
        self.assertIn('La continuidad debe estudiarse', extract)
        self.assertNotIn('Introducción. Introducción.', extract)
        self.assertLessEqual(len(extract), 18000)

    def test_technical_question_49_is_retained(self):
        source = ('Contenido introductorio. '*600 +
                  '48 . ¿ Cuál es la vigencia de la autorización concedida ?\n'
                  'La autorización inicial se concede por un año.\n'
                  '49 . ¿ Qué debo hacer cuando expire ?\n'
                  'En los dos meses previos o en los tres posteriores se solicita la modificación conforme al artículo 191.\n'
                  '50 . ¿ Cómo puedo trabajar ?\nLa respuesta cambia según la autorización.\n')
        result = official.excerpt_for_procedure_guidance(source)
        self.assertIn('En los dos meses previos', result)
        self.assertIn('artículo 191', result)

    def test_only_post_grant_evidence_in_readiness(self):
        plan={'commercial_classification':{'business_category':'regularizacion_2026'},'topic':'Cómo continuar la residencia extraordinaria','group':'arraigo'}
        def e(eid,source,article='',title='',url=''):
            return {'evidence_id':eid,'source_id':source,'article':article,'document_title':title,'official_url':url,'authority':source,'text':'source text'}
        records=[e('E1','BOE-A-2024-24099','191'),e('E2','BOE-A-2024-24099','64'),
                 e('E3','boe',url='https://www.boe.es/diario_boe/txt.php?id=BOE-A-2026-8284'),
                 e('E4','migraciones',title='Ministerio: preguntas sobre modificación o prórroga tras la regularización'),
                 e('E5','migraciones',title='Hoja 28 Ter — arraigo extraordinario')]
        selected,excluded=legal.focused_evidence_for_topic(plan,records)
        self.assertEqual([e['evidence_id'] for e in selected], ['E1','E3','E4'])
        self.assertEqual(len(excluded),2)

    def test_other_categories_unmodified(self):
        plan={'commercial_classification':{'business_category':'cuenta_ajena'},'topic':'Renovación cuenta ajena','group':'renewal'}
        data=[{'evidence_id':'X','source_id':'boe'}]
        self.assertEqual(legal.focused_evidence_for_topic(plan,data),(data,[]))

if __name__=='__main__':unittest.main()
