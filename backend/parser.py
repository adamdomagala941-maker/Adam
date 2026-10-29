"""Conservative SDS text extraction. Unavailable facts stay empty; no LLM guesses."""
from __future__ import annotations

import io
import re
from html.parser import HTMLParser
from pypdf import PdfReader

FIELDS = ("name", "cas", "ec", "formula", "molarMass", "signalWord", "hazards", "precautions", "supplemental")
CODE = re.compile(r"(?<![A-Za-z0-9])(?:EUH\d{3}|[HP]\d{3})(?:\s*\+\s*(?:EUH\d{3}|[HP]\d{3}))*\b")
SECTION = re.compile(r"(?im)^\s*(?:SEKCJA|SECTION|ROZDZIAŁ)\s+(\d{1,2})\s*[:.\- ]")


class DocumentError(ValueError):
    pass


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if not self.hidden and tag in {"p", "div", "br", "h1", "h2", "h3", "tr", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False
        if not self.hidden and tag in {"p", "div", "h1", "h2", "h3", "tr", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if not self.hidden:
            self.parts.append(data)


def read_document(content: bytes, content_type: str = "", filename: str = "") -> tuple[str, str]:
    if content.lstrip().startswith(b"%PDF-"):
        try:
            reader = PdfReader(io.BytesIO(content), strict=False)
            if reader.is_encrypted and not reader.decrypt(""):
                raise DocumentError("Plik PDF jest zaszyfrowany. Wczytaj niezabezpieczoną kartę.")
            if len(reader.pages) > 120:
                raise DocumentError("PDF ma więcej niż 120 stron. Wczytaj samą kartę charakterystyki produktu.")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError("Nie udało się odczytać pliku PDF. Sprawdź, czy plik nie jest uszkodzony.") from exc
        if len(text.strip()) < 60:
            raise DocumentError("PDF nie zawiera czytelnej warstwy tekstowej (prawdopodobnie skan). Wczytaj kartę z tekstem lub uzupełnij etykietę ręcznie.")
        return text[:500_000], "PDF — odczyt warstwy tekstowej"
    if "html" in content_type or content.lstrip().startswith((b"<!DOCTYPE", b"<!doctype", b"<html")):
        parser = VisibleText()
        parser.feed(content.decode("utf-8", errors="replace"))
        return "".join(parser.parts)[:500_000], "HTML — odczyt tekstu"
    if "text/plain" in content_type or filename.lower().endswith(".txt"):
        return content.decode("utf-8-sig", errors="replace")[:500_000], "Tekst karty"
    raise DocumentError("Obsługiwane są karty PDF, strony HTML i pliki TXT. Dokumenty Word i makra nie są uruchamiane.")


def clean(text: str) -> str:
    return re.sub(r"[ \t\u00a0]+", " ", text.replace("\r", "\n").replace("\x00", "")).strip()


def section(text: str, number: int) -> str:
    matches = list(SECTION.finditer(text))
    for index, match in enumerate(matches):
        if int(match.group(1)) == number:
            end = matches[index+1].start() if index+1 < len(matches) else len(text)
            return text[match.end():end]
    # A few SDS omit the word SEKCJA / SECTION but retain "2. IDENTYFIKACJA...".
    heading = re.search(rf"(?im)^\s*{number}\.\s+(?:[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ /-]{{6,}})", text)
    if heading:
        end = re.search(rf"(?im)^\s*{number+1}\.\s+(?:[A-ZĄĆĘŁŃÓŚŹŻ][A-ZĄĆĘŁŃÓŚŹŻ /-]{{6,}})", text[heading.end():])
        return text[heading.end():heading.end()+end.start()] if end else text[heading.end():]
    return ""


def labeled_value(text: str, labels: str, *, max_length: int = 160) -> str:
    pattern = re.compile(rf"(?im)(?:^|\n)\s*(?:{labels})\s*[:：]?\s*([^\n]*)")
    match = pattern.search(text)
    if not match:
        return ""
    value = match.group(1).strip(" :\t")
    if not value:
        tail = text[match.end():]
        value = next((line.strip() for line in tail.splitlines() if line.strip()), "")
    return value[:max_length]


def cas_valid(cas: str) -> bool:
    digits = cas.replace("-", "")
    return len(digits) >= 5 and sum(int(d)*i for i, d in enumerate(reversed(digits[:-1]), 1)) % 10 == int(digits[-1])


def unique_matches(pattern: str, text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(pattern, text)))


def statement_map(labeling: str) -> dict[str, str]:
    matches = list(CODE.finditer(labeling))
    result = {}
    for index, match in enumerate(matches):
        code = re.sub(r"\s+", "", match.group())
        end = matches[index+1].start() if index+1 < len(matches) else len(labeling)
        body = labeling[match.end():end]
        # Stop at the next named subsection/header instead of swallowing a page.
        body = re.split(r"(?im)^\s*(?:2\.[1-9]|SEKCJA|SECTION|Hasło ostrzegawcze|Signal word|Piktogram|Hazard pictogram|Zwroty wskazujące|Zwroty określające|Informacje uzupełniające|Dodatkowe informacje|Supplemental|Other hazards|Inne zagrożenia|Elementy oznakowania|Strona\s+\d|Page\s+\d)\b", body)[0]
        body = " ".join(body.split()).strip(" :;.-\u2022")
        # An isolated code in a classification table is not a complete statement.
        if body and not re.match(r"^(?:Skin |Eye |STOT |Flam\.|Acute |Asp\.|Aquatic )", body):
            # Repeated codes with the same/shorter content are ignored.
            if code not in result or len(body) < len(result[code]):
                result[code] = body[:2500]
    return result


def parse_sds(text: str, *, expected_name: str = "", title: str = "", url: str = "", method: str = "Tekst karty") -> dict:
    text = clean(text)
    one, two, three, nine = (section(text, n) for n in (1, 2, 3, 9))
    if not two:
        raise DocumentError("Nie rozpoznano sekcji 2 karty charakterystyki. Dokument może być stroną wyszukiwania lub mieć nietypowy układ. Wczytaj bezpośrednio PDF; dane można też wpisać ręcznie.")
    warnings = ["Sprawdź produkt, stężenie i aktualność karty. Odczyt automatyczny wymaga porównania z oryginałem przed drukiem."]
    labeling = two
    start = re.search(r"(?m)^\s*2\.2\.?\s*", two)
    if start:
        labeling = two[start.end():]
    else:
        warnings.append("Nie rozpoznano podsekcji 2.2. Zwroty odczytano z całej sekcji 2; sprawdź dobór zwrotów do etykiety.")
    end = re.search(r"(?m)^\s*2\.3\.?\s*", labeling)
    if end:
        labeling = labeling[:end.start()]
    data = {field: "" for field in FIELDS}
    data.update(volume="", catalogNumber="", pictograms=[])
    data["name"] = labeled_value(one, r"(?:Nazwa (?:produktu|substancji|handlowa)|Nazwa chemiczna|Product name|Trade name|Chemical name|Nazwa)\b")
    if not data["name"]:
        warnings.append("Nie odczytano jednoznacznej nazwy produktu z sekcji 1. Uzupełnij ją z karty.")
    elif expected_name and expected_name.casefold() not in data["name"].casefold():
        warnings.append(f"Karta identyfikuje produkt jako „{data['name']}”. Porównaj z wyszukiwaną nazwą „{expected_name}”.")
    identifiers = one + "\n" + three
    cas_candidates = [cas for cas in unique_matches(r"\b\d{2,7}-\d{2}-\d\b", identifiers) if cas_valid(cas)]
    primary_cas = [cas for cas in unique_matches(r"\b\d{2,7}-\d{2}-\d\b", one) if cas_valid(cas)]
    if len(primary_cas) == 1:
        data["cas"] = primary_cas[0]
    elif len(cas_candidates) == 1:
        data["cas"] = cas_candidates[0]
        warnings.append("CAS odczytano z sekcji składu. Dla mieszaniny może to być CAS składnika, a nie całego produktu.")
    elif len(cas_candidates) > 1:
        warnings.append("Karta zawiera kilka numerów CAS (" + ", ".join(cas_candidates[:8]) + "). Nie wybrano składnika automatycznie.")
    ec_candidates = unique_matches(r"\b[2-9]\d{2}-\d{3}-\d\b", identifiers)
    primary_ec = unique_matches(r"\b[2-9]\d{2}-\d{3}-\d\b", one)
    if len(primary_ec) == 1:
        data["ec"] = primary_ec[0]
    elif len(ec_candidates) == 1:
        data["ec"] = ec_candidates[0]
    elif len(ec_candidates) > 1:
        warnings.append("Kilka numerów WE w karcie — wybierz właściwy ręcznie.")
    data["formula"] = labeled_value(one + "\n" + nine + "\n" + three, r"Wzór (?:chemiczny|sumaryczny|cząsteczkowy)|Molecular formula|Chemical formula", max_length=80)
    mass = labeled_value(one + "\n" + nine + "\n" + three, r"Masa (?:molowa|cząsteczkowa)|Molar mass|Molecular (?:weight|mass)", max_length=80)
    number = re.search(r"\d+(?:[,.]\d+)?", mass)
    data["molarMass"] = number.group() if number else ""
    signal = re.search(r"\b(Niebezpieczeństwo|Uwaga|Danger|Warning)\b", labeling, flags=re.I)
    if signal:
        data["signalWord"] = {"danger": "NIEBEZPIECZEŃSTWO", "warning": "UWAGA"}.get(signal.group().lower(), signal.group().upper())
    statements = statement_map(labeling)
    data["hazards"] = "\n".join(f"{code} {body}" for code, body in statements.items() if code.startswith("H"))
    data["precautions"] = "\n".join(f"{code} {body}" for code, body in statements.items() if code.startswith("P"))
    data["supplemental"] = "\n".join(f"{code} {body}" for code, body in statements.items() if code.startswith("EUH"))
    data["pictograms"] = list(dict.fromkeys(re.findall(r"\bGHS0[1-9]\b", labeling, flags=re.I)))
    data["pictograms"] = [code.upper() for code in data["pictograms"]]
    if not data["pictograms"]:
        warnings.append("Nie odczytano kodów GHS. Piktogramy bywają obrazami w PDF — wybierz je ręcznie na podstawie sekcji 2.2.")
    if re.search(r"\b(?:Danger|Warning|Hazard statements|Precautionary statements)\b", labeling, re.I) and not re.search(r"\b(?:Niebezpieczeństwo|Uwaga|Zwroty)\b", labeling, re.I):
        warnings.append("Karta wygląda na anglojęzyczną. Zwroty pozostają w języku źródła; uzupełnij zatwierdzone polskie brzmienie.")
    missing = [field for field in ("name", "cas", "ec", "formula", "molarMass", "signalWord", "hazards", "precautions", "pictograms") if not data[field]]
    return {"data": data, "source": {"title": title or data["name"] or "Karta charakterystyki", "url": url, "method": method,
            "excerpt": labeling[:9000], "evidence": {"identity": one[:5000], "composition": three[:5000], "labeling": labeling[:12000], "properties": nine[:5000]}},
            "warnings": warnings, "missing": missing}
