"""HTTP API and optional built frontend. Run: uvicorn backend.app:app."""
from __future__ import annotations

from pathlib import Path
import ipaddress
import re
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .network import MAX_DOCUMENT_BYTES, RetrievalError, fetch_document
from .parser import DocumentError, parse_sds, read_document
from .pictograms import detect_pdf_pictograms
from .search import search_sds
from .resolver import extract_from_url
from .ai_search import search_with_ai
from .settings import SettingsError, load_settings, public_settings, save_settings

app = FastAPI(title="DJCHEM · Etykiety", version="1.1.0")


class ExtractRequest(BaseModel):
    url: str = Field(min_length=8, max_length=3000)
    expected_name: str = Field(default="", max_length=200)


class SettingsRequest(BaseModel):
    ai_enabled: bool
    openai_api_key: str | None = Field(default=None, repr=False)
    clear_key: bool = False


def require_local_settings(request: Request):
    """A local desktop app must not expose secret configuration to LAN clients.

    Require loopback client and same-origin browser requests (prevents blind
    cross-site writes to a localhost API). CLI loopback requests may omit Origin.
    """
    try:
        if not request.client or not ipaddress.ip_address(request.client.host).is_loopback:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=403, detail="Ustawienia klucza API można zmieniać wyłącznie lokalnie na komputerze, na którym działa serwer.")
    expected = urlsplit(str(request.base_url))
    if expected.hostname not in {"localhost", "127.0.0.1", "::1"} or request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise HTTPException(status_code=403, detail="Dostęp do klucza i płatnego wyszukiwania AI wymaga otwarcia aplikacji pod lokalnym adresem na tym komputerze.")
    origin = request.headers.get("origin")
    if origin:
        try:
            parsed = urlsplit(origin)
            origin_port = parsed.port
        except ValueError:
            raise HTTPException(status_code=403, detail="Nieprawidłowy adres źródłowy żądania ustawień.")
        # Vite development proxy keeps the browser's Origin on port 5173.
        local_dev = parsed.hostname in {"localhost", "127.0.0.1", "::1"} and origin_port == 5173
        if not local_dev and (parsed.scheme, parsed.netloc) != (expected.scheme, expected.netloc):
            raise HTTPException(status_code=403, detail="Ustawienia należy zapisać z okna aplikacji na tym komputerze.")


@app.get("/api/settings")
def read_search_settings():
    try:
        return public_settings()
    except SettingsError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/settings")
def write_search_settings(body: SettingsRequest, request: Request):
    require_local_settings(request)
    try:
        return save_settings(body.ai_enabled, body.openai_api_key, body.clear_key)
    except SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def extract_content(content: bytes, content_type: str = "", filename: str = "", *, expected_name: str = "", title: str = "", url: str = "") -> dict:
    text, method = read_document(content, content_type, filename)
    result = parse_sds(text, expected_name=expected_name, title=title, url=url, method=method)
    expected_percent = set(re.findall(r"\d+(?:[,.]\d+)?\s*%", expected_name))
    expected_percent = {value.replace(" ", "").replace(",", ".") for value in expected_percent}
    product_percent = {value.replace(" ", "").replace(",", ".") for value in re.findall(r"\d+(?:[,.]\d+)?\s*%", result["data"]["name"])}
    if expected_percent and product_percent and not expected_percent.intersection(product_percent):
        raise DocumentError("Karta dotyczy produktu o innym stężeniu: „" + result["data"]["name"] + "”. Nie zastosowano jej do wyszukiwanego produktu „" + expected_name + "”.")
    if expected_percent and not product_percent:
        result["warnings"].append("Nie potwierdzono stężenia " + ", ".join(sorted(expected_percent)) + " w odczytanej nazwie produktu. Sprawdź stężenie i skład w dokumencie źródłowym.")
    if content.lstrip().startswith(b"%PDF-") and not result["data"]["pictograms"]:
        detected = detect_pdf_pictograms(content)
        if detected:
            result["data"]["pictograms"] = detected
            result["missing"] = [field for field in result["missing"] if field != "pictograms"]
            result["warnings"] = [warning for warning in result["warnings"] if not warning.startswith("Nie odczytano kodów GHS.")]
            result["warnings"].append("Piktogramy " + ", ".join(detected) + " rozpoznano graficznie w sekcji 2.2. Porównaj wszystkie symbole z oryginałem karty; nierozpoznane obrazy mogą wymagać ręcznego wskazania.")
            result["source"]["evidence"]["pictograms"] = "Wizualne dopasowanie standardowych symboli w sekcji 2.2 PDF: " + ", ".join(detected)
    return result


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "DJCHEM labels", "version": "1.1.0"}


@app.get("/api/search")
def search(request: Request, q: str = Query(min_length=2, max_length=200)):
    if len(q.strip()) < 2:
        raise HTTPException(status_code=422, detail="Wpisz co najmniej dwa znaki nazwy produktu.")
    warnings = []
    try:
        settings = load_settings()
        if settings["ai_enabled"]:
            require_local_settings(request)
            try:
                results = search_with_ai(q.strip(), settings["openai_api_key"])
                return {"results": results, "warnings": ["Źródła wyszukano z AI. Dane etykiety są odczytywane z dokumentów, nie generowane przez model. Porównaj produkt, stężenie i aktualność karty."]}
            except RetrievalError as exc:
                warnings.append(str(exc))
        result = search_sds(q.strip())
        result["warnings"] = warnings + result["warnings"]
        return result
    except RetrievalError as exc:
        message = " ".join(warnings + [str(exc)])
        raise HTTPException(status_code=503, detail=message) from exc
    except SettingsError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/extract")
def extract(body: ExtractRequest):
    try:
        return extract_from_url(body.url, expected_name=body.expected_name, extract_content=extract_content)
    except RetrievalError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except DocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    try:
        content = bytearray()
        while chunk := await file.read(1024 * 1024):
            content.extend(chunk)
            if len(content) > MAX_DOCUMENT_BYTES:
                raise HTTPException(status_code=413, detail="Plik przekracza 15 MB. Wczytaj mniejszą kartę.")
        return await run_in_threadpool(extract_content, bytes(content), file.content_type or "", file.filename or "", title=file.filename or "Wczytana karta")
    except DocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await file.close()


# A production build is served from the same origin. Development Vite proxies
# /api to this process. Do not expose arbitrary filesystem paths in the fallback.
DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if DIST.is_dir():
    assets = DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Nieznany punkt API.")
        candidate = (DIST / path).resolve()
        if candidate.is_relative_to(DIST) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
