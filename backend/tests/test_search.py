import os
import unittest
from unittest.mock import MagicMock, patch

from backend.network import RetrievalError
from backend.search import (
    _ddgs_search, _normalized_url, query_variants, rank_results,
    relevance_score, search_aliases, search_sds,
)


class QueryTests(unittest.TestCase):
    def test_deha_aliases_preserve_requested_85_percent(self):
        aliases = search_aliases('Dwuetylohydroksyloamina 85% Chempur')
        self.assertEqual(aliases, ['Dwuetylohydroksyloamina 85% Chempur',
                                  'dietylohydroksyloamina 85% Chempur',
                                  'N,N-diethylhydroxylamine 85% Chempur'])
        self.assertTrue(all('85%' in alias and 'Chempur' in alias for alias in aliases))

    def test_query_languages_do_not_require_polish_and_english_terms_together(self):
        variants = query_variants('Dwuetylohydroksyloamina 85%')
        self.assertIn('dietylohydroksyloamina 85%', variants[0][0])
        self.assertIn('karta charakterystyki', variants[0][0])
        self.assertNotIn('SDS', variants[0][0])
        self.assertIn('N,N-diethylhydroxylamine 85%', variants[1][0])
        self.assertIn('safety data sheet', variants[1][0])
        self.assertEqual([region for _, region in variants], ['pl-pl', 'us-en'])

    def test_unrecognized_name_not_rewritten_or_given_safety_facts(self):
        self.assertEqual(search_aliases('Produkt złożony 12,5% dostawca'), ['Produkt złożony 12,5% dostawca'])


class RankingTests(unittest.TestCase):
    def test_correct_concentration_sds_outranks_pure_substance_and_generic_page(self):
        results = [
            {'title':'Karty charakterystyki', 'url':'https://supplier.example/catalog'},
            {'title':'N,N-diethylhydroxylamine 99% Safety Data Sheet', 'url':'https://supplier.example/pure.pdf'},
            {'title':'N,N-diethylhydroxylamine 85% Safety Data Sheet', 'url':'https://supplier.example/solution.pdf'},
            {'title':'Dietylohydroksyloamina 85% — produkt', 'url':'https://supplier.example/product'},
        ]
        ranked = rank_results(results, 'Dwuetylohydroksyloamina 85%')
        self.assertEqual(ranked[0]['url'], 'https://supplier.example/solution.pdf')
        self.assertGreater(relevance_score(ranked[0], 'Dwuetylohydroksyloamina 85%'),
                           relevance_score(results[1], 'Dwuetylohydroksyloamina 85%'))

    def test_normalizes_tracking_and_duplicates_without_losing_document_query(self):
        results = [{'title':'Aceton karta charakterystyki', 'url':'https://supplier.example/get?id=12&utm_source=search#page=1'},
                   {'title':'Aceton', 'url':'https://supplier.example/get?id=12'}]
        ranked = rank_results(results, 'aceton')
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]['url'], 'https://supplier.example/get?id=12')

    def test_cas_query_prioritizes_matching_identifier(self):
        results = [{'title':'Safety Data Sheet 64-17-5','url':'https://supplier.example/ethanol.pdf'},
                   {'title':'Safety Data Sheet 67-64-1','url':'https://supplier.example/acetone.pdf'}]
        self.assertEqual(rank_results(results, '67-64-1')[0]['url'], 'https://supplier.example/acetone.pdf')

    def test_search_pages_private_targets_and_credential_urls_removed(self):
        for url in ['https://www.bing.com/search?q=aceton', 'https://search.brave.com/search?q=x',
                    'http://127.0.0.1/card.pdf', 'http://169.254.169.254/',
                    'https://a:b@supplier.example/card.pdf', 'file:///tmp/card.pdf']:
            with self.subTest(url=url):
                self.assertEqual(_normalized_url(url), '')
        self.assertEqual(rank_results([{'url':'https://supplier.example/card.pdf','title':'Aceton'}], 'aceton')[0]['url'],
                         'https://supplier.example/card.pdf')


class ProviderTests(unittest.TestCase):
    def test_ddgs_preserves_proxy_and_ca_verification(self):
        instance = MagicMock()
        instance.text.return_value = [{'title':'Aceton SDS','href':'https://supplier.example/card.pdf','body':'source snippet'}]
        with patch('backend.search.DDGS', return_value=instance) as factory, patch.dict(os.environ, {
            'HTTPS_PROXY':'http://proxy.example:8080', 'SSL_CERT_FILE':'/trusted/ca.pem'
        }):
            results = _ddgs_search('aceton karta charakterystyki', region='pl-pl')
        factory.assert_called_once_with(proxy='http://proxy.example:8080', timeout=8, verify='/trusted/ca.pem')
        self.assertEqual(instance.text.call_args.kwargs['backend'], 'brave,mojeek')
        self.assertEqual(results[0]['url'], 'https://supplier.example/card.pdf')
        self.assertEqual(results[0]['body'], 'source snippet')

    def test_relevant_first_query_avoids_unnecessary_network_calls(self):
        hit = {'title':'Dietylohydroksyloamina 85% karta charakterystyki','url':'https://supplier.example/deha.pdf'}
        with patch('backend.search._ddgs_search', return_value=[hit]) as ddgs, patch('backend.search.fetch_document') as legacy:
            result = search_sds('Dwuetylohydroksyloamina 85%')
        self.assertEqual(result['results'][0]['url'], hit['url'])
        self.assertEqual(ddgs.call_count, 1)
        legacy.assert_not_called()

    def test_second_language_retry_used_after_first_no_result(self):
        hit = {'title':'N,N-diethylhydroxylamine 85% Safety Data Sheet','url':'https://supplier.example/deha.pdf'}
        with patch('backend.search._ddgs_search', side_effect=[RetrievalError('none'),[hit]]) as ddgs:
            result = search_sds('Dwuetylohydroksyloamina 85%')
        self.assertEqual(ddgs.call_count, 2)
        self.assertEqual(ddgs.call_args.kwargs['region'], 'us-en')
        self.assertEqual(result['results'][0]['url'], hit['url'])

    def test_bing_rss_remains_fallback(self):
        rss = b'<rss><channel><item><title>Aceton karta charakterystyki</title><link>https://supplier.example/aceton.pdf</link></item></channel></rss>'
        with patch('backend.search._ddgs_search', side_effect=RetrievalError('blocked')) as ddgs, \
             patch('backend.search.fetch_document', return_value=(rss,'application/rss+xml','https://www.bing.com/search')) as legacy:
            result = search_sds('aceton')
        self.assertEqual(ddgs.call_count, 2)
        self.assertEqual(legacy.call_count, 1)
        self.assertEqual(result['results'][0]['provider'], 'Bing')

    def test_all_blocked_is_error_not_fake_empty_success(self):
        with patch('backend.search._ddgs_search', side_effect=RetrievalError('blocked')) as ddgs, \
             patch('backend.search.fetch_document', side_effect=RetrievalError('blocked')) as legacy:
            with self.assertRaisesRegex(RetrievalError, 'niedostępne'):
                search_sds('aceton')
        self.assertEqual(ddgs.call_count, 2)
        self.assertEqual(legacy.call_count, 2)

    def test_completed_empty_search_is_distinct_from_blocked(self):
        with patch('backend.search._ddgs_search', return_value=[]), \
             patch('backend.search.fetch_document', side_effect=RetrievalError('blocked')):
            result = search_sds('nieistniejąca nazwa')
        self.assertEqual(result['results'], [])
        self.assertTrue(any('Nie znaleziono' in warning for warning in result['warnings']))

    def test_elapsed_budget_prevents_starting_more_requests(self):
        with patch('backend.search.time.monotonic', side_effect=[0,36,36,36]), \
             patch('backend.search._ddgs_search') as ddgs, patch('backend.search.fetch_document') as legacy:
            with self.assertRaises(RetrievalError):
                search_sds('aceton')
        ddgs.assert_not_called()
        legacy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
