"""Follow explicit SDS links on producer/product pages to the actual document.

No URLs are synthesized from chemical names. Every HTTP request uses the common
bounded downloader, including its redirect and public-address validation.
"""
from __future__ import annotations

from collections import deque
from html.parser import HTMLParser
import re
import unicodedata
from typing import Callable
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from .network import RetrievalError, fetch_document
from .parser import DocumentError

MAX_DOCUMENTS = 6
MAX_DEPTH = 2
SAFETY = re.compile(r"karta[ _/-]*(?:charakterystyk|bezpieczenstw)|charakterystyk|safety[ _/-]*data|material[ _/-]*safety|sicherheitsdatenblatt|fiche[ _/-]*de[ _/-]*donnees[ _/-]*de[ _/-]*securite|(?:^|[^a-z])m?sds(?:[^a-z]|$)")
MANUAL = re.compile(r"instrukcj|manual|certificate|certyfikat|technical[ _-]*data|specyfikacj")


def folded(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold().replace('ł', 'l')) if not unicodedata.combining(c))


class SDSLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.active: dict | None = None
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {'script', 'style', 'noscript'}:
            self.hidden += 1
        if self.hidden:
            return
        if tag == 'a' and attrs.get('href'):
            self._finish()
            label = ' '.join(attrs.get(k, '') for k in ('title', 'aria-label', 'data-type', 'download'))
            self.active = {'url': attrs['href'], 'parts': [label]}
        if tag in {'iframe', 'embed', 'object'}:
            url = attrs.get('src') or attrs.get('data') or ''
            if url and ('pdf' in attrs.get('type', '').lower() or SAFETY.search(folded(url))):
                self.links.append((url, 'karta charakterystyki PDF'))

    def handle_data(self, data):
        if self.active and not self.hidden:
            self.active['parts'].append(data)

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'noscript'}:
            self.hidden = max(0, self.hidden - 1)
        if tag == 'a':
            self._finish()

    def _finish(self):
        if self.active:
            self.links.append((self.active['url'], ' '.join(self.active['parts'])))
            self.active = None

    def close(self):
        self._finish()
        super().close()


def document_links(content: bytes, page_url: str, expected_name: str = '') -> list[str]:
    parser = SDSLinks()
    parser.feed(content[:2_000_000].decode('utf-8', errors='replace'))
    parser.close()
    ranked: dict[str, int] = {}
    query_words = set(re.findall(r'[a-z]{4,}', folded(expected_name)))
    for href, label in parser.links:
        candidate = urljoin(page_url, href.strip())
        parts = urlsplit(candidate)
        if parts.scheme not in {'http', 'https'} or not parts.hostname:
            continue
        candidate = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ''))
        words = folded(unquote(candidate) + ' ' + label)
        if not SAFETY.search(words) or (MANUAL.search(words) and not SAFETY.search(folded(label))):
            continue
        score = 10
        if '.pdf' in parts.path.lower():
            score += 6
        if 'karta' in folded(label) or 'charakterystyk' in words:
            score += 5
        if re.search(r'(?:[/_.?=&-])pl(?:[/_.?=&-]|$)|polski|polish', words):
            score += 4
        if parts.hostname == urlsplit(page_url).hostname:
            score += 1
        score += sum(word in words for word in query_words)
        ranked[candidate] = max(ranked.get(candidate, 0), score)
    return sorted(ranked, key=lambda url: ranked[url], reverse=True)[:MAX_DOCUMENTS]


def _is_html(content: bytes, content_type: str) -> bool:
    return 'html' in content_type.lower() or content.lstrip().lower().startswith((b'<!doctype html', b'<html'))


def extract_from_url(url: str, expected_name: str = '', *, extract_content: Callable) -> dict:
    """Try the URL, then up to five explicitly linked SDS documents/pages.

    The callback has the same arguments as backend.app.extract_content. A product
    page is never accepted as a source merely because its title mentions SDS.
    """
    pending = deque([(url, 0, [])])
    visited: set[str] = set()
    errors: list[str] = []
    pdf_errors: list[str] = []
    root_html = False
    while pending and len(visited) < MAX_DOCUMENTS:
        current, depth, trail = pending.popleft()
        if current in visited:
            continue
        visited.add(current)
        try:
            content, content_type, final_url = fetch_document(current)
        except RetrievalError as exc:
            if depth == 0:
                raise
            errors.append(str(exc))
            continue
        is_html = _is_html(content, content_type)
        if depth == 0:
            root_html = is_html
        try:
            result = extract_content(content, content_type, final_url, expected_name=expected_name, url=final_url)
            if trail:
                result['source']['landingUrl'] = url
                result['source'].setdefault('evidence', {})['discovery'] = {'pages': trail, 'document': final_url}
                result['warnings'].append('Kartę znaleziono przez odnośnik na stronie produktu. Źródłem danych jest wskazany dokument, nie opis handlowy.')
            return result
        except DocumentError as exc:
            errors.append(str(exc))
            if content.lstrip().startswith(b'%PDF-'):
                pdf_errors.append(str(exc))
        if is_html and depth < MAX_DEPTH:
            links = document_links(content, final_url, expected_name)
            for link in links:
                if link not in visited:
                    pending.append((link, depth + 1, trail + [final_url]))
    if pdf_errors:
        raise DocumentError('Znaleziono dokument PDF, ale nie udało się odczytać karty: ' + pdf_errors[0])
    if root_html:
        detail = (' Odczyt odnośników zakończył się błędem: ' + errors[-1]) if len(visited) > 1 and errors else ''
        raise DocumentError('Znaleziono stronę produktu, ale nie odnaleziono dostępnej karty charakterystyki PDF/HTML w jej odnośnikach.' + detail + ' Wklej bezpośredni adres karty albo wgraj PDF.')
    raise DocumentError(errors[0] if errors else 'Nie udało się odczytać karty charakterystyki ze wskazanego źródła.')
