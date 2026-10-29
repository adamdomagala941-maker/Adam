"""Bounded HTTP retrieval via the platform's inherited proxy and CA trust."""
from __future__ import annotations

import ipaddress
import json
import os
import socket
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

MAX_DOCUMENT_BYTES = 15 * 1024 * 1024
MANAGED_POLICY_PATH = Path("/etc/codex/network-policy.json")
USER_AGENT = "DJCHEM-Label/1.0 (Safety Data Sheet reader)"


class RetrievalError(ValueError):
    pass


def managed_proxy(host: str | None = None) -> str | None:
    """Trust only the platform's fixed sidecar and its explicit restricted list.

    The managed executor intentionally has no external DNS route. For listed
    destinations, the trusted egress sidecar resolves names and enforces policy.
    This fallback is never enabled for unrestricted policies, wildcard entries,
    arbitrary proxies or hosts missing from the policy snapshot.
    """
    try:
        policy = json.loads(MANAGED_POLICY_PATH.read_text())
        route = policy.get("http_proxy")
        inherited = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        http_policy = policy.get("http_network_policy", {})
        if policy.get("version") != 1 or route != "http://proxy:8080" or inherited != route or http_policy.get("type") != "restricted":
            return None
        if host is not None:
            explicit = {rule.get("host", "").rstrip(".").lower() for rule in http_policy.get("egress_rules", [])}
            if host not in explicit:
                return None
        return route
    except (OSError, ValueError, TypeError):
        return None


def validate_public_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
        if parts.scheme not in {"https", "http"} or not parts.hostname:
            raise RetrievalError("Podaj pełny adres HTTP lub HTTPS karty charakterystyki.")
        if parts.username or parts.password or parts.port not in {None, 80, 443}:
            raise RetrievalError("Adres nie może zawierać danych logowania ani niestandardowego portu.")
        host = parts.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
            raise RetrievalError("Adresy lokalne i prywatne nie są obsługiwane.")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None:
            if not address.is_global:
                raise RetrievalError("Adresy lokalne i prywatne nie są obsługiwane.")
            return url.strip()
        try:
            answers = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except OSError as exc:
            if managed_proxy(host):
                return url.strip()
            raise RetrievalError("Nie można zweryfikować publicznego adresu serwera karty. W środowisku chmurowym dodaj domenę dostawcy do dozwolonych adresów i zapisz ustawienia; możesz też wczytać PDF.") from exc
        if not answers or any(not ipaddress.ip_address(answer[4][0]).is_global for answer in answers):
            raise RetrievalError("Adresy lokalne i prywatne nie są obsługiwane.")
        return url.strip()
    except RetrievalError:
        raise
    except (ValueError, OSError) as exc:
        raise RetrievalError("Nie można zweryfikować publicznego adresu serwera karty.") from exc


def fetch_document(url: str, *, max_bytes: int = MAX_DOCUMENT_BYTES) -> tuple[bytes, str, str]:
    current = url
    try:
        with httpx.Client(proxy=managed_proxy(), timeout=httpx.Timeout(25.0, connect=10.0), follow_redirects=False, trust_env=True,
                          headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html,text/plain,application/xml"}) as client:
            for _ in range(6):
                current = validate_public_url(current)
                with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise RetrievalError("Serwer zwrócił przekierowanie bez adresu docelowego.")
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 400:
                        if response.status_code == 403:
                            raise RetrievalError("Serwer lub polityka sieciowa odmówiły dostępu (HTTP 403). Użyj pliku PDF lub innego źródła.")
                        raise RetrievalError(f"Nie udało się pobrać dokumentu (HTTP {response.status_code}).")
                    if int(response.headers.get("content-length", "0") or "0") > max_bytes:
                        raise RetrievalError("Dokument jest zbyt duży (maksymalnie 15 MB).")
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > max_bytes:
                            raise RetrievalError("Dokument jest zbyt duży (maksymalnie 15 MB).")
                    return bytes(data), response.headers.get("content-type", ""), str(response.url)
            raise RetrievalError("Zbyt wiele przekierowań podczas pobierania karty.")
    except RetrievalError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise RetrievalError("Nie udało się połączyć ze źródłem karty. Sprawdź adres i dostęp sieciowy; możesz też wczytać plik PDF.") from exc
