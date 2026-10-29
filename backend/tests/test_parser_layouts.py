import unittest

from backend.parser import parse_sds, read_document, section
from backend.tests.test_backend import SDS


class ParserLayoutTests(unittest.TestCase):
    def test_compacted_section_headers(self):
        text = SDS.replace('SEKCJA ', 'SEKCJA')
        result = parse_sds(text)
        self.assertEqual(result['data']['cas'], '78-83-1')
        self.assertIn('H226', result['data']['hazards'])
        self.assertNotIn('H999', result['data']['hazards'])

    def test_english_headers_without_colon(self):
        text = SDS.replace('SEKCJA ', 'SECTION ').replace(': Identyfikacja', ' Identification').replace(': Skład', ' Composition').replace(': Właściwości', ' Properties').replace(': Inne', ' Other')
        self.assertIn('H226', parse_sds(text)['data']['hazards'])

    def test_title_case_numbered_headers_without_section_word(self):
        text = SDS
        for number in (1, 2, 3, 9, 16):
            text = text.replace(f'SEKCJA {number}:', f'{number}.')
        result = parse_sds(text)
        self.assertEqual(result['data']['cas'], '78-83-1')
        self.assertIn('H315', result['data']['hazards'])
        self.assertNotIn('H999', result['data']['hazards'])

    def test_spaced_subsection_labels(self):
        result = parse_sds(SDS.replace('2.2', '2 . 2').replace('2.3', '2 . 3'))
        self.assertIn('H226', result['data']['hazards'])
        self.assertNotIn('PBT', result['data']['precautions'])

    def test_repeated_continuation_heading_retains_statement(self):
        text = SDS.replace('P210 Przechowywać', 'SEKCJA 2: kontynuacja\nP210 Przechowywać')
        self.assertIn('P210', parse_sds(text)['data']['precautions'])

    def test_html_table_cells_are_not_joined(self):
        html = b'<html><table><tr><td>Nazwa produktu:</td><td>Aceton</td></tr><tr><td>CAS:</td><td>67-64-1</td></tr></table></html>'
        text, _ = read_document(html, 'text/html')
        self.assertIn('Nazwa produktu:\nAceton', text.replace('\n\n', '\n'))

    def test_subsection_does_not_become_major_section(self):
        self.assertIn('2.2', section(SDS, 2))
        self.assertNotIn('Masa molowa', section(SDS, 2))


if __name__ == '__main__':
    unittest.main()
