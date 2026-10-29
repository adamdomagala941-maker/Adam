import unittest
from unittest.mock import patch

from backend.network import RetrievalError
from backend.parser import DocumentError
from backend.resolver import MAX_DOCUMENTS, document_links, extract_from_url


def extracted(content, content_type, filename, **kwargs):
    if content != b'%PDF-real-sds':
        raise DocumentError('Nie rozpoznano sekcji 2 karty charakterystyki.')
    return {'data': {'name': 'Dietylohydroksyloamina 85%'}, 'source': {'url': kwargs['url'], 'evidence': {}}, 'warnings': [], 'missing': []}


class ResolverTests(unittest.TestCase):
    def test_product_page_follows_explicit_relative_polish_sds_link(self):
        landing = b'<html><a href="/manual.pdf">Instrukcja</a><a href="../docs/deha-sds-pl.pdf">Karta charakterystyki PL</a></html>'
        responses = {
            'https://producer.example/product/deha': (landing, 'text/html', 'https://producer.example/product/deha'),
            'https://producer.example/docs/deha-sds-pl.pdf': (b'%PDF-real-sds', 'application/pdf', 'https://cdn.example/deha.pdf'),
        }
        with patch('backend.resolver.fetch_document', side_effect=lambda url: responses[url]) as fetch:
            result = extract_from_url('https://producer.example/product/deha', 'Dwuetylohydroksyloamina 85%', extract_content=extracted)
        self.assertEqual(result['source']['url'], 'https://cdn.example/deha.pdf')
        self.assertEqual(result['source']['landingUrl'], 'https://producer.example/product/deha')
        self.assertEqual(fetch.call_count, 2)

    def test_document_url_is_used_directly(self):
        with patch('backend.resolver.fetch_document', return_value=(b'%PDF-real-sds', 'application/pdf', 'https://docs.example/sds.pdf')) as fetch:
            result = extract_from_url('https://docs.example/sds.pdf', extract_content=extracted)
        self.assertEqual(fetch.call_count, 1)
        self.assertNotIn('landingUrl', result['source'])

    def test_pdf_only_heading_error_is_preserved(self):
        with patch('backend.resolver.fetch_document', return_value=(b'%PDF-scanned', 'application/pdf', 'https://docs.example/sds.pdf')):
            with self.assertRaisesRegex(DocumentError, 'Znaleziono dokument PDF.*sekcji 2'):
                extract_from_url('https://docs.example/sds.pdf', extract_content=extracted)

    def test_product_page_with_no_sds_reports_actual_problem(self):
        with patch('backend.resolver.fetch_document', return_value=(b'<html>Product text</html>', 'text/html', 'https://docs.example/product')):
            with self.assertRaisesRegex(DocumentError, 'stronę produktu.*nie odnaleziono'):
                extract_from_url('https://docs.example/product', extract_content=extracted)

    def test_two_level_download_page_is_resolved(self):
        responses = {
            'https://docs.example/product': (b'<html><a href="/sds">Safety Data Sheet</a></html>', 'text/html', 'https://docs.example/product'),
            'https://docs.example/sds': (b'<html><a href="/deha-pl.pdf">Karta charakterystyki</a></html>', 'text/html', 'https://docs.example/sds'),
            'https://docs.example/deha-pl.pdf': (b'%PDF-real-sds', 'application/pdf', 'https://docs.example/deha-pl.pdf'),
        }
        with patch('backend.resolver.fetch_document', side_effect=lambda url: responses[url]):
            result = extract_from_url('https://docs.example/product', extract_content=extracted)
        self.assertEqual(len(result['source']['evidence']['discovery']['pages']), 2)

    def test_root_network_denial_is_not_disguised(self):
        with patch('backend.resolver.fetch_document', side_effect=RetrievalError('HTTP 403')):
            with self.assertRaisesRegex(RetrievalError, '403'):
                extract_from_url('https://docs.example/sds.pdf', extract_content=extracted)

    def test_private_link_is_still_checked_by_common_downloader(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if url == 'https://docs.example/product':
                return b'<html><a href="http://127.0.0.1/sds.pdf">SDS</a></html>', 'text/html', url
            raise RetrievalError('Adresy lokalne i prywatne nie są obsługiwane.')
        with patch('backend.resolver.fetch_document', side_effect=fetch):
            with self.assertRaisesRegex(DocumentError, 'prywatne'):
                extract_from_url('https://docs.example/product', extract_content=extracted)
        self.assertEqual(calls[-1], 'http://127.0.0.1/sds.pdf')

    def test_requests_are_bounded_and_loops_not_followed(self):
        links = ''.join(f'<a href="/sds{i}">SDS</a>' for i in range(20)) + '<a href="/root">SDS</a>'
        def fetch(url):
            return ('<html>'+links+'</html>').encode(), 'text/html', url
        with patch('backend.resolver.fetch_document', side_effect=fetch) as fetcher:
            with self.assertRaises(DocumentError):
                extract_from_url('https://docs.example/root', extract_content=extracted)
        self.assertLessEqual(fetcher.call_count, MAX_DOCUMENTS)

    def test_links_prioritize_polish_pdf_and_ignore_script_and_manual(self):
        html = b'''<a href="/deha-sds-en.pdf">Safety data sheet EN</a>
        <a href="/deha-sds-pl.pdf">Karta charakterystyki PL</a>
        <a href="javascript:download('/sds.pdf')">SDS</a>
        <script><a href="/sds-script.pdf">SDS</a></script>
        <a href="/manual.pdf">Instrukcja</a>'''
        links = document_links(html, 'https://docs.example/product')
        self.assertEqual(links[0], 'https://docs.example/deha-sds-pl.pdf')
        self.assertEqual(len(links), 2)


if __name__ == '__main__':
    unittest.main()
