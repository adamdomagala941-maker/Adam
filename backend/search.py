"""Public search providers, with honest reporting of blocked/unavailable searches."""
from __future__ import annotations

import html
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse
from xml.etree import ElementTree

from .network import RetrievalError, fetch_document


class SearchHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self.active = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "result__a" in attrs.get("class", ""):
            self.active = attrs.get("href", "")
            self.parts = []

    def handle_data(self, data):
        if self.active is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.active is not None:
            href = html.unescape(self.active)
            if href.startswith("//"):
                href = "https:" + href
            query = parse_qs(urlparse(href).query)
            href = query.get("uddg", [href])[0]
            if href.startswith(("http://", "https://")):
                self.results.append({"title": "".join(self.parts).strip(), "url": href, "provider": "DuckDuckGo"})
            self.active = None


def search_sds(name: str) -> dict:
    query = f'{name} "karta charakterystyki" SDS filetype:pdf'
    warnings = []
    completed = 0
    try:
        data, _, _ = fetch_document("https://www.bing.com/search?" + urlencode({"q": query, "format": "rss"}), max_bytes=2*1024*1024)
        root = ElementTree.fromstring(data)
        if root.tag.lower() != "rss":
            raise RetrievalError("Wyszukiwarka Bing nie udostępniła wyników RSS.")
        completed += 1
        results = []
        for item in root.findall(".//item"):
            url = item.findtext("link", "").strip()
            title = item.findtext("title", "").strip()
            if url.startswith(("https://", "http://")):
                results.append({"title": title or url, "url": url, "provider": "Bing"})
        if results:
            return {"results": _dedupe(results), "warnings": warnings}
    except (RetrievalError, ElementTree.ParseError):
        warnings.append("Wyszukiwanie Bing jest obecnie niedostępne lub blokowane przez sieć.")
    try:
        data, _, _ = fetch_document("https://html.duckduckgo.com/html/?" + urlencode({"q": query}), max_bytes=2*1024*1024)
        parser = SearchHTML()
        body = data.decode("utf-8", errors="replace")
        parser.feed(body)
        if "anomaly" in body.lower() or "bots use duckduckgo" in body.lower():
            raise RetrievalError("Wyszukiwarka wymaga potwierdzenia CAPTCHA.")
        completed += 1
        if parser.results:
            return {"results": _dedupe(parser.results), "warnings": warnings}
    except RetrievalError:
        warnings.append("Wyszukiwanie DuckDuckGo jest obecnie niedostępne, blokowane lub wymaga CAPTCHA.")
    if not completed:
        raise RetrievalError("Automatyczne wyszukiwanie jest niedostępne: Bing i DuckDuckGo nie odpowiadają lub są blokowane. Wklej adres karty albo wczytaj PDF. W środowisku chmurowym wymagany jest dostęp do www.bing.com, html.duckduckgo.com oraz domeny dostawcy karty.")
    return {"results": [], "warnings": warnings + ["Nie znaleziono karty dla podanej nazwy. Spróbuj pełnej nazwy handlowej i producenta lub wczytaj PDF."]}


def _dedupe(results):
    seen = set()
    unique = []
    for result in results:
        if result["url"] not in seen:
            seen.add(result["url"])
            unique.append(result)
    return unique[:10]
