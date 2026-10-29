"""Integration regressions: selected sources, key opt-in and product formulation."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import app, extract_content
from backend.network import RetrievalError
from backend.parser import DocumentError
from backend.tests.test_backend import SDS, pdf_fixture


class SearchApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = patch('backend.settings.SETTINGS_PATH', Path(self.temp.name)/'private'/'settings.json')
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.env = patch.dict(os.environ, {'DJCHEM_OPENAI_API_KEY':''})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 50001))

    def test_default_search_never_bills_ai(self):
        with patch('backend.app.search_with_ai') as ai, patch('backend.app.search_sds', return_value={'results': [], 'warnings': []}):
            response = self.client.get('/api/search', params={'q':'Dwuetylohydroksyloamina 85%'})
        self.assertEqual(response.status_code, 200)
        ai.assert_not_called()

    def test_settings_key_never_returned_and_enabled_search_uses_ai_sources(self):
        key = 'test-not-a-real-key'
        response = self.client.post('/api/settings', json={'ai_enabled':True, 'openai_api_key':key}, headers={'Origin':'http://127.0.0.1'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn(key,response.text)
        self.assertTrue(self.client.get('/api/settings').json()['key_configured'])
        source={'title':'SDS 85%', 'url':'https://manufacturer.example/sds.pdf','provider':'OpenAI Web Search'}
        with patch('backend.app.search_with_ai',return_value=[source]) as ai, patch('backend.app.search_sds') as standard:
            result=self.client.get('/api/search',params={'q':'Dwuetylohydroksyloamina 85%'})
        self.assertEqual(result.json()['results'],[source])
        ai.assert_called_once_with('Dwuetylohydroksyloamina 85%',key)
        standard.assert_not_called()

    def test_ai_failure_uses_standard_search_with_explanation(self):
        self.client.post('/api/settings',json={'ai_enabled':True,'openai_api_key':'test-not-a-real-key'})
        with patch('backend.app.search_with_ai',side_effect=RetrievalError('API chwilowo niedostępne')), patch('backend.app.search_sds',return_value={'results':[], 'warnings':[]}):
            result=self.client.get('/api/search',params={'q':'aceton'})
        self.assertEqual(result.status_code,200)
        self.assertIn('API chwilowo niedostępne',result.json()['warnings'])

    def test_enable_without_key_rejected(self):
        result=self.client.post('/api/settings',json={'ai_enabled':True})
        self.assertEqual(result.status_code,400)
        self.assertIn('klucz',result.json()['detail'])

    def test_cross_site_or_remote_settings_writes_rejected(self):
        response=self.client.post('/api/settings',json={'ai_enabled':False},headers={'Origin':'https://external.example'})
        self.assertEqual(response.status_code,403)
        with TestClient(app,client=('192.0.2.10',50001)) as remote:
            self.assertEqual(remote.post('/api/settings',json={'ai_enabled':False}).status_code,403)

    def test_cross_site_paid_search_never_calls_ai(self):
        self.client.post('/api/settings',json={'ai_enabled':True,'openai_api_key':'test-not-a-real-key'})
        with patch('backend.app.search_with_ai') as ai:
            result=self.client.get('/api/search',params={'q':'aceton'},headers={'Sec-Fetch-Site':'cross-site'})
        self.assertEqual(result.status_code,403)
        ai.assert_not_called()

    def test_dns_rebinding_host_cannot_change_key(self):
        result=self.client.post('/api/settings',json={'ai_enabled':False},headers={'Host':'external.example','Origin':'http://external.example'})
        self.assertEqual(result.status_code,403)

    def test_product_page_follows_to_actual_pdf_and_retains_source(self):
        root='https://manufacturer.example/product/85'
        pdf_url='https://manufacturer.example/files/sds-pl.pdf'
        fixture=SDS.replace('ALKOHOL IZOBUTYLOWY','N,N-DIETYLOHYDROKSYLOAMINA 85%')
        # Test structure only, never a real SDS for this product: generated fixture
        # deliberately reuses an existing parser test body without chemical claims.
        html=b'<html><a href="/files/sds-pl.pdf">Karta charakterystyki PL</a></html>'
        responses={root:(html,'text/html',root),pdf_url:(pdf_fixture(fixture),'application/pdf',pdf_url)}
        with patch('backend.resolver.fetch_document',side_effect=lambda url:responses[url]):
            result=self.client.post('/api/extract',json={'url':root,'expected_name':'Dwuetylohydroksyloamina 85%'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['source']['url'],pdf_url)
        self.assertEqual(result.json()['source']['landingUrl'],root)
        self.assertIn('85%',result.json()['data']['name'])

    def test_other_concentration_is_not_automatically_accepted(self):
        text=SDS.replace('ALKOHOL IZOBUTYLOWY','N,N-DIETYLOHYDROKSYLOAMINA 99%')
        with self.assertRaisesRegex(DocumentError,'innym stężeniu'):
            extract_content(text.encode(),'text/plain',expected_name='Dwuetylohydroksyloamina 85%')

    def test_unconfirmed_concentration_warns_without_manufacturing_data(self):
        result=extract_content(SDS.encode(),'text/plain',expected_name='produkt 85%')
        self.assertTrue(any('Nie potwierdzono stężenia 85%' in warning for warning in result['warnings']))


if __name__=='__main__':
    unittest.main()
