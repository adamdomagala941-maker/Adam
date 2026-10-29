import json
import unittest
from unittest.mock import patch

import httpx

from backend.ai_search import API_URL, AISearchError, search_with_ai


def response_body():
    return {
        "id": "resp_test",
        "status": "completed",
        "output": [
            {"id": "ws_test", "type": "web_search_call", "status": "completed", "action": {"type": "search", "queries": ["aceton SDS"], "sources": [
                {"type": "url", "url": "https://manufacturer.test.pl/acetone.pdf"},
                {"type": "url", "url": "http://127.0.0.1/private"},
            ]}},
            {"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "Karta [tu](https://invented.example.net/fake.pdf)", "annotations": [
                {"type": "url_citation", "url": "https://manufacturer.test.pl/acetone.pdf", "title": "Aceton — karta charakterystyki", "start_index": 0, "end_index": 5},
                {"type": "url_citation", "url": "https://supplier.test.pl/sds/aceton", "title": "Karta SDS"},
            ]}]},
        ],
    }


class AISearchTests(unittest.TestCase):
    def call_with_response(self, status=200, body=None, content=None):
        calls = []
        def handler(request):
            calls.append(request)
            if content is not None:
                return httpx.Response(status, content=content)
            return httpx.Response(status, json=response_body() if body is None else body)
        original = httpx.Client
        with patch('backend.ai_search.managed_proxy', return_value=None), patch('backend.ai_search.httpx.Client', side_effect=lambda **kwargs: original(transport=httpx.MockTransport(handler), trust_env=False, follow_redirects=False)):
            results = search_with_ai('aceton Chempur', 'test-secret-key')
        return results, calls

    def test_uses_real_citations_not_freeform_urls(self):
        results, calls = self.call_with_response()
        self.assertEqual([r['url'] for r in results], ['https://manufacturer.test.pl/acetone.pdf', 'https://supplier.test.pl/sds/aceton'])
        self.assertEqual(results[0]['title'], 'Aceton — karta charakterystyki')
        self.assertNotIn('invented', json.dumps(results))
        self.assertEqual(str(calls[0].url), API_URL)
        self.assertEqual(calls[0].headers['authorization'], 'Bearer test-secret-key')
        payload = json.loads(calls[0].content)
        self.assertEqual(payload['tools'][0]['type'], 'web_search')
        self.assertEqual(payload['tool_choice'], {'type': 'web_search'})
        self.assertFalse(payload['store'])
        self.assertIn('web_search_call.action.sources', payload['include'])
        self.assertIn('"aceton Chempur"', payload['input'])

    def test_no_key_makes_no_request(self):
        with patch('backend.ai_search.httpx.Client') as client:
            with self.assertRaisesRegex(AISearchError, 'klucz OpenAI API'):
                search_with_ai('aceton', '')
            client.assert_not_called()

    def test_considered_sources_without_selected_citations_are_not_accepted(self):
        body = response_body()
        body['output'] = body['output'][:1]
        with self.assertRaisesRegex(AISearchError, 'cytowaniem'):
            self.call_with_response(body=body)

    def test_missing_completed_search_is_not_faked(self):
        body = response_body()
        body['output'] = body['output'][1:]
        with self.assertRaisesRegex(AISearchError, 'nie wykonało'):
            self.call_with_response(body=body)

    def test_does_not_send_credentials_to_redirect(self):
        with self.assertRaisesRegex(AISearchError, 'HTTP 302'):
            self.call_with_response(status=302)

    def test_public_url_filter_and_deduplication(self):
        body = response_body()
        body['output'][0]['action']['sources'] += [
            {'type': 'url', 'url': 'http://169.254.169.254/private'},
            {'type': 'url', 'url': 'https://user:secret@site.test.pl/a.pdf'},
            {'type': 'url', 'url': 'https://localhost/private'},
            {'type': 'url', 'url': 'file:///tmp/sds.pdf'},
            {'type': 'url', 'url': 'https://www.test.pl:9000/sds.pdf'},
            {'type': 'url', 'url': 'https://manufacturer.test.pl/acetone.pdf#section2'},
        ]
        results, _ = self.call_with_response(body=body)
        self.assertEqual(len(results), 2)

    def test_invalid_json_is_explained_without_key_or_response(self):
        with self.assertRaises(AISearchError) as caught:
            self.call_with_response(content=b'not json; test-secret-key')
        self.assertNotIn('test-secret-key', str(caught.exception))
        self.assertIn('nieczyteln', str(caught.exception))

    def test_auth_and_quota_errors(self):
        for status, phrase in [(401, 'odmówiło'), (403, 'odmówiło'), (429, 'brak środków'), (400, 'model'), (500, 'niedostępne')]:
            with self.subTest(status=status), self.assertRaisesRegex(AISearchError, phrase):
                self.call_with_response(status=status, body={'error': {'message': 'test-secret-key'}})

    def test_incomplete_response_is_not_accepted(self):
        body = response_body()
        body['status'] = 'incomplete'
        with self.assertRaisesRegex(AISearchError, 'nie zostało ukończone'):
            self.call_with_response(body=body)

    def test_at_most_eight_results(self):
        body = response_body()
        body['output'][1]['content'][0]['annotations'] += [{'type': 'url_citation', 'url': f'https://manufacturer.test.pl/{i}.pdf','title':f'Karta {i}'} for i in range(20)]
        results, _ = self.call_with_response(body=body)
        self.assertEqual(len(results), 8)


if __name__ == '__main__':
    unittest.main()
