"""Bounded, multi-engine SDS discovery, preserving the requested formulation.

Search aliases change query spelling only. They never supply hazard data or
silently substitute a pure substance for the requested concentration.
"""
from __future__ import annotations

import html
import ipaddress
import os
import re
import time
import unicodedata
from html.parser import HTMLParser
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlsplit, urlunsplit
from xml.etree import ElementTree

from .network import RetrievalError, fetch_document

try:
    from ddgs import DDGS
except ImportError:  # Existing installations still retain their legacy providers.
    DDGS = None

DDGS_TIMEOUT = 8
MAX_DDGS_QUERIES = 2
SEARCH_BUDGET_SECONDS = 35
SEARCH_PROVIDER_HOSTS = (
    "search.brave.com", "www.mojeek.com", "search.yahoo.com",
    "www.bing.com", "html.duckduckgo.com",
)


def _fold(text: str) -> str:
    # Ł does not decompose under NFKD.
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower().replace("ł", "l")) if not unicodedata.combining(c))


def search_aliases(name: str) -> list[str]:
    name = re.sub(r"\s+", " ", name).strip()
    variants = [name]
    if re.search(r"(?:dwuetylo|dietylo)hydroksyloamina", name, re.I):
        variants.append(re.sub(r"(?:dwuetylo|dietylo)hydroksyloamina", "dietylohydroksyloamina", name, flags=re.I))
        variants.append(re.sub(r"(?:dwuetylo|dietylo)hydroksyloamina", "N,N-diethylhydroxylamine", name, flags=re.I))
    return list(dict.fromkeys(variants))


def query_variants(name: str) -> list[tuple[str, str]]:
    aliases = search_aliases(name)
    polish = next((alias for alias in aliases if alias.lower().startswith("dietylohydroksyloamina")), aliases[0])
    english = next((alias for alias in aliases if "diethylhydroxylamine" in alias.lower()), aliases[0])
    # The Polish query must not additionally require the literal English "SDS".
    return [
        (f'{polish} "karta charakterystyki" filetype:pdf', "pl-pl"),
        (f'{english} "safety data sheet"', "us-en"),
    ]


def _ddgs_search(query: str, *, region: str = "pl-pl") -> list[dict]:
    if DDGS is None:
        raise RetrievalError("Moduł wyszukiwania nie jest zainstalowany. Uruchom ponownie launcher, aby zaktualizować zależności.")
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    # Respect configured CA trust. Never set verify=False to work around failures.
    verify = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE") or True
    engines = "brave,mojeek" if region == "pl-pl" else "yahoo,duckduckgo"
    try:
        results = DDGS(proxy=proxy, timeout=DDGS_TIMEOUT, verify=verify).text(
            query, region=region, max_results=8, backend=engines,
        )
    except Exception as exc:
        raise RetrievalError("Wyszukiwarki nie udostępniły wyników (blokada sieci, limit lub CAPTCHA).") from exc
    return [{"title": str(item.get("title") or ""), "url": str(item.get("href") or item.get("url") or ""),
             "provider": "DDGS · " + engines.replace(",", "/"), "body": str(item.get("body") or "")}
            for item in results]


def _normalized_url(url: str) -> str:
    try:
        parts = urlsplit(html.unescape(url).strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            return ""
        host = parts.hostname.rstrip(".").lower()
        if parts.port not in {None, 80, 443} or host == "localhost" or host.endswith((".local", ".localhost", ".internal")) or "." not in host:
            return ""
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global:
                return ""
        except ValueError:
            pass
        if any(host == engine or host.endswith("." + engine) for engine in
               ("bing.com", "google.com", "duckduckgo.com", "search.brave.com", "mojeek.com", "search.yahoo.com")):
            return ""
        query = sorted((key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                       if not key.lower().startswith("utm_") and key.lower() not in {"gclid", "fbclid", "msclkid"})
        netloc = host if parts.port is None else f"{host}:{parts.port}"
        return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", urlencode(query), ""))
    except (TypeError, ValueError):
        return ""


def relevance_score(result: dict, name: str) -> float:
    title = str(result.get("title") or "")
    text = _fold(" ".join((title, str(result.get("body") or ""), str(result.get("url") or ""))))
    scores = []
    for alias in search_aliases(name):
        tokens = [t for t in re.findall(r"[a-z0-9]+", _fold(alias)) if len(t) > 2 and not t.isdigit()]
        matches = sum(token in text for token in tokens)
        scores.append(30 * matches / len(tokens) if tokens else 0)
    score = max(scores, default=0)
    requested_cas = re.findall(r"\b\d{2,7}-\d{2}-\d\b", name)
    if requested_cas and any(cas in text for cas in requested_cas):
        score += 40
    if urlsplit(result.get("url", "")).path.lower().endswith(".pdf"):
        score += 14
    if any(term in text for term in ("karta charakterystyki", "safety data sheet", "material safety data")):
        score += 14
    elif re.search(r"\b(?:sds|msds)\b", text):
        score += 8
    percentages = re.findall(r"\b\d+(?:[.,]\d+)?\s*%", name)
    if percentages:
        requested = {p.replace(" ", "").replace(",", ".") for p in percentages}
        mentioned = {p.replace(" ", "").replace(",", ".") for p in re.findall(r"\b\d+(?:[.,]\d+)?\s*%", text)}
        if requested & mentioned:
            score += 24
        elif mentioned:
            score -= 30
    return score


def rank_results(results: list[dict], name: str) -> list[dict]:
    unique = {}
    for item in results:
        url = _normalized_url(str(item.get("url") or ""))
        if not url:
            continue
        result = {**item, "url": url, "title": str(item.get("title") or url)}
        if url not in unique or relevance_score(result, name) > relevance_score(unique[url], name):
            unique[url] = result
    return sorted(unique.values(), key=lambda r: relevance_score(r, name), reverse=True)[:10]


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
    warnings = []
    completed = 0
    results = []
    started = time.monotonic()
    variants = query_variants(name)
    for query, region in variants[:MAX_DDGS_QUERIES]:
        if time.monotonic() - started >= SEARCH_BUDGET_SECONDS:
            break
        try:
            found = _ddgs_search(query, region=region)
            completed += 1
            results.extend(found)
            ranked = rank_results(results, name)
            # Search a second language when the first provider returned only
            # generic pages or a product with a different concentration.
            if ranked and relevance_score(ranked[0], name) >= 50:
                return {"results": ranked, "warnings": warnings}
        except RetrievalError:
            warnings.append(f"Wyszukiwanie {'polskie' if region == 'pl-pl' else 'angielskie'} w module wielosilnikowym jest niedostępne lub nie zwróciło wyników.")
    if results:
        ranked = rank_results(results, name)
        if ranked:
            return {"results": ranked, "warnings": warnings}
    # Compatibility fallbacks for endpoints that remain accessible when a
    # metasearch engine is unavailable. At most two further requests are made;
    # each network operation retains the bounded retrieval timeout.
    query = variants[0][0]
    try:
        if time.monotonic() - started >= SEARCH_BUDGET_SECONDS:
            raise RetrievalError("Osiągnięto limit czasu wyszukiwania.")
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
            ranked = rank_results(results, name)
            if ranked:
                return {"results": ranked, "warnings": warnings}
    except (RetrievalError, ElementTree.ParseError):
        warnings.append("Wyszukiwanie Bing jest obecnie niedostępne lub blokowane przez sieć.")
    try:
        if time.monotonic() - started >= SEARCH_BUDGET_SECONDS:
            raise RetrievalError("Osiągnięto limit czasu wyszukiwania.")
        data, _, _ = fetch_document("https://html.duckduckgo.com/html/?" + urlencode({"q": query}), max_bytes=2*1024*1024)
        parser = SearchHTML()
        body = data.decode("utf-8", errors="replace")
        parser.feed(body)
        if "anomaly" in body.lower() or "bots use duckduckgo" in body.lower():
            raise RetrievalError("Wyszukiwarka wymaga potwierdzenia CAPTCHA.")
        completed += 1
        if parser.results:
            ranked = rank_results(parser.results, name)
            if ranked:
                return {"results": ranked, "warnings": warnings}
    except RetrievalError:
        warnings.append("Wyszukiwanie DuckDuckGo jest obecnie niedostępne, blokowane lub wymaga CAPTCHA.")
    if not completed:
        raise RetrievalError("Automatyczne wyszukiwanie jest niedostępne: wyszukiwarki nie odpowiadają, są blokowane lub wymagają CAPTCHA. Skonfiguruj w programie wyszukiwanie AI/API, wklej adres karty albo wczytaj PDF. W środowisku chmurowym wymagany jest dostęp do " + ", ".join(SEARCH_PROVIDER_HOSTS) + " oraz domeny dostawcy karty.")
    return {"results": [], "warnings": warnings + ["Nie znaleziono karty dla podanej nazwy. Spróbuj pełnej nazwy handlowej i producenta lub wczytaj PDF."]}


def _dedupe(results):
    """Legacy helper retained for callers; search results use relevance ranking."""
    return rank_results(results, "")
