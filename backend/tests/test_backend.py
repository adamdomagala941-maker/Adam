import io
import json
import os
from pathlib import Path
import tempfile
import httpx
import socket
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.app import app
from backend.network import RetrievalError, validate_public_url, fetch_document
from backend.parser import DocumentError, cas_valid, parse_sds, read_document
from backend.search import SearchHTML

SDS = """SEKCJA 1: Identyfikacja substancji
1.1 Identyfikator produktu
Nazwa produktu: ALKOHOL IZOBUTYLOWY
Numer CAS: 78-83-1
Numer WE: 201-148-0
Wzór sumaryczny: C4H10O
Masa molowa: 74,12 g/mol
SEKCJA 2: Identyfikacja zagrożeń
2.1 Klasyfikacja substancji
Flam. Liq. 3 H226
2.2 Elementy oznakowania
Piktogramy: GHS02 GHS05 GHS07
Hasło ostrzegawcze: NIEBEZPIECZEŃSTWO
Zwroty wskazujące rodzaj zagrożenia
H226 Łatwopalna ciecz i pary.
H315 Działa drażniąco na skórę.
H318 Powoduje poważne uszkodzenie oczu.
H335 Może powodować podrażnienie dróg oddechowych.
H336 Może wywoływać uczucie senności lub zawroty głowy.
Zwroty określające środki ostrożności
P210 Przechowywać z dala od źródeł ciepła. Nie palić.
P302+P352 W PRZYPADKU KONTAKTU ZE SKÓRĄ:
Umyć dużą ilością wody z mydłem.
P305 + P351 + P338 W PRZYPADKU DOSTANIA SIĘ DO OCZU: Ostrożnie płukać wodą.
Informacje uzupełniające
EUH066 Powtarzające się narażenie może powodować wysuszanie skóry.
2.3 Inne zagrożenia
Nie zawiera PBT.
SEKCJA 3: Skład
78-83-1 201-148-0 99%
SEKCJA 9: Właściwości fizyczne i chemiczne
Masa molowa: 74,12 g/mol
SEKCJA 16: Inne informacje
H999 TEGO ZWROTU NIE WOLNO POBRAĆ Z SEKCJI 16.
"""


def pdf_fixture(text):
    """Generate an actual PDF with a selectable text layer for integration tests."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=850)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    commands = ["BT /F1 8 Tf 30 810 Td 11 TL"]
    for line in text.splitlines():
        line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({line}) Tj T*")
    commands.append("ET")
    stream.set_data("\n".join(commands).encode("latin-1", errors="replace"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class ParserTests(unittest.TestCase):
    def test_labeling_not_classification_or_section16(self):
        result = parse_sds(SDS)
        data = result["data"]
        self.assertEqual(data["cas"], "78-83-1")
        self.assertEqual(data["ec"], "201-148-0")
        self.assertEqual(data["name"], "ALKOHOL IZOBUTYLOWY")
        self.assertEqual(data["molarMass"], "74,12")
        self.assertEqual(data["pictograms"], ["GHS02", "GHS05", "GHS07"])
        self.assertEqual(data["hazards"].count("H226"), 1)
        self.assertNotIn("H999", data["hazards"])
        self.assertNotIn("PBT", data["precautions"])
        self.assertIn("P305+P351+P338", data["precautions"])
        self.assertIn("Umyć dużą ilością", data["precautions"])
        self.assertNotIn("Zwroty określające", data["hazards"])
        self.assertTrue(data["supplemental"].startswith("EUH066"))

    def test_mixture_does_not_pick_arbitrary_cas(self):
        mixture = SDS.replace("Numer CAS: 78-83-1", "").replace("78-83-1 201-148-0 99%", "78-83-1 50%\n64-17-5 50%")
        result = parse_sds(mixture)
        self.assertEqual(result["data"]["cas"], "")
        self.assertTrue(any("kilka numerów CAS" in warning for warning in result["warnings"]))

    def test_missing_fields_are_not_invented(self):
        result = parse_sds("SEKCJA 1: Produkt\nSEKCJA 2: Zagrożenia\n2.2 Elementy oznakowania\nBrak danych.\nSEKCJA 3: Skład", expected_name="aceton")
        self.assertEqual(result["data"]["name"], "")
        self.assertEqual(result["data"]["pictograms"], [])
        self.assertIn("name", result["missing"])

    def test_rejects_unrelated_webpage(self):
        with self.assertRaises(DocumentError):
            parse_sds("Search results for chemical safety data sheet")

    def test_cas_checksum(self):
        self.assertTrue(cas_valid("78-83-1"))
        self.assertFalse(cas_valid("78-83-2"))

    def test_real_pdf_layer_read(self):
        text, method = read_document(pdf_fixture(SDS), "application/pdf")
        result = parse_sds(text)
        self.assertEqual(result["data"]["cas"], "78-83-1")
        self.assertEqual(result["data"]["ec"], "201-148-0")
        self.assertIn("PDF", method)

    def test_image_only_pdf_rejected(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        output = io.BytesIO()
        writer.write(output)
        with self.assertRaisesRegex(DocumentError, "warstwy tekstowej"):
            read_document(output.getvalue())


class NetworkTests(unittest.TestCase):
    def test_private_and_loopback_blocked(self):
        for url in ["http://localhost/a", "https://app.internal/", "http://127.0.0.1/", "http://10.0.0.5/", "http://169.254.169.254/", "http://[::1]/"]:
            with self.subTest(url=url), self.assertRaises(RetrievalError):
                validate_public_url(url)

    def test_credentials_ports_and_non_http_blocked(self):
        for url in ["file:///etc/passwd", "ftp://example.com/a", "https://a:b@example.com/", "https://example.com:9999/a"]:
            with self.subTest(url=url), self.assertRaises(RetrievalError):
                validate_public_url(url)

    def test_mixed_public_private_dns_blocked(self):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)), (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]
        with patch("backend.network.socket.getaddrinfo", return_value=answers), self.assertRaises(RetrievalError):
            validate_public_url("https://public.example/card.pdf")

    def test_managed_dns_fallback_requires_explicit_policy_host(self):
        policy = {"version": 1, "http_proxy": "http://proxy:8080", "http_network_policy": {"type": "restricted", "egress_rules": [{"host": "docs.example.com"}]}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(policy))
            with patch("backend.network.MANAGED_POLICY_PATH", path), patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy:8080"}), patch("backend.network.socket.getaddrinfo", side_effect=socket.gaierror("proxy-only DNS")):
                self.assertEqual(validate_public_url("https://docs.example.com/sds.pdf"), "https://docs.example.com/sds.pdf")
                with self.assertRaises(RetrievalError):
                    validate_public_url("https://unknown.example.com/sds.pdf")
                with self.assertRaises(RetrievalError):
                    validate_public_url("https://127.0.0.1/sds.pdf")
                policy["http_network_policy"]["type"] = "unrestricted"
                path.write_text(json.dumps(policy))
                with self.assertRaises(RetrievalError):
                    validate_public_url("https://docs.example.com/sds.pdf")

    def test_redirect_to_private_ip_is_never_requested(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})
        original_client = httpx.Client
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("backend.network.socket.getaddrinfo", return_value=answers), patch("backend.network.httpx.Client", side_effect=lambda **kwargs: original_client(transport=httpx.MockTransport(handler), trust_env=False)):
            with self.assertRaisesRegex(RetrievalError, "lokalne"):
                fetch_document("https://public.example.com/sds.pdf")
        self.assertEqual(calls, ["https://public.example.com/sds.pdf"])

    def test_search_unwraps_ddg_result(self):
        parser = SearchHTML()
        parser.feed('<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fsds.pdf">Karta <b>acetonu</b></a>')
        self.assertEqual(parser.results[0]["url"], "https://example.com/sds.pdf")
        self.assertEqual(parser.results[0]["title"], "Karta acetonu")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        self.assertEqual(self.client.get("/api/health").json()["status"], "ok")

    def test_upload_pdf_and_extract(self):
        response = self.client.post("/api/upload", files={"file": ("test-sds.pdf", pdf_fixture(SDS), "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["cas"], "78-83-1")
        self.assertEqual(response.json()["source"]["title"], "test-sds.pdf")

    def test_image_pictograms_integrated_when_text_codes_missing(self):
        no_codes = SDS.replace("GHS02 GHS05 GHS07", "[obrazy]")
        with patch("backend.app.detect_pdf_pictograms", return_value=["GHS02", "GHS05"]):
            response = self.client.post("/api/upload", files={"file": ("card.pdf", pdf_fixture(no_codes), "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["data"]["pictograms"], ["GHS02", "GHS05"])
        self.assertNotIn("pictograms", result["missing"])
        self.assertTrue(any("graficznie" in warning for warning in result["warnings"]))
        self.assertIn("Wizualne", result["source"]["evidence"]["pictograms"])

    def test_unsafe_url_returns_explained_error(self):
        response = self.client.post("/api/extract", json={"url": "http://127.0.0.1/secrets"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("lokalne", response.json()["detail"])

    def test_blocked_search_does_not_pretend_no_results(self):
        with patch("backend.search.fetch_document", side_effect=RetrievalError("Denied")):
            response = self.client.get("/api/search", params={"q": "aceton"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("niedostępne", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
