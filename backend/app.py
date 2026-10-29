"""HTTP API and optional built frontend. Run: uvicorn backend.app:app."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .network import MAX_DOCUMENT_BYTES, RetrievalError, fetch_document
from .parser import DocumentError, parse_sds, read_document
from .pictograms import detect_pdf_pictograms
from .search import search_sds

app = FastAPI(title="DJCHEM · Etykiety", version="1.0.0")


class ExtractRequest(BaseModel):
    url: str = Field(min_length=8, max_length=3000)
    expected_name: str = Field(default="", max_length=200)


def extract_content(content: bytes, content_type: str = "", filename: str = "", *, expected_name: str = "", title: str = "", url: str = "") -> dict:
    text, method = read_document(content, content_type, filename)
    result = parse_sds(text, expected_name=expected_name, title=title, url=url, method=method)
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
    return {"status": "ok", "service": "DJCHEM labels"}


@app.get("/api/search")
def search(q: str = Query(min_length=2, max_length=200)):
    if len(q.strip()) < 2:
        raise HTTPException(status_code=422, detail="Wpisz co najmniej dwa znaki nazwy produktu.")
    try:
        return search_sds(q.strip())
    except RetrievalError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/extract")
def extract(body: ExtractRequest):
    try:
        content, content_type, final_url = fetch_document(body.url)
        return extract_content(content, content_type, body.url, expected_name=body.expected_name, url=final_url)
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
