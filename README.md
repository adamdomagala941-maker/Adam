# DJCHEM — studio etykiet

Aplikacja w języku polskim działająca w przeglądarce. Edytor i generator PDF pracują lokalnie w przeglądarce; serwer Python wyszukuje i odczytuje karty charakterystyki. Nie wymaga płatnego klucza API.

## Uruchomienie

**Paczka ZIP zawiera już zbudowany interfejs.** Po rozpakowaniu na Windows zainstaluj Python 3.11+ i uruchom `Uruchom.bat`. Na macOS/Linux: `python3 launcher.py`. Launcher przygotuje zależności (pierwsze uruchomienie wymaga internetu) i otworzy aplikację w przeglądarce. Pozostaw okno serwera otwarte. Nie potrzebujesz Node.js, aby korzystać z gotowej paczki.

Poniższe polecenia służą do uruchomienia z kodu źródłowego i przebudowania interfejsu:

Wymagane: Python 3.11+, Node.js 20.19+ (lub 22.12+), dostęp do internetu przy instalacji i wyszukiwaniu.

```bash
cd /workspace/Adam # poza chmurą: katalog pobranego projektu
python -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ..
bash start.sh
```

Następnie otwórz w przeglądarce adres lokalnego serwera na porcie 8000. Na Windows polecenie aktywacji to `.venv\Scripts\activate`, instalacja `python -m pip install -r backend/requirements.txt`, a start: `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`. Aby udostępnić usługę poza komputerem, ustaw `HOST=0.0.0.0`; aplikacja nie ma kont użytkowników, dlatego publiczne wdrożenie wymaga własnej kontroli dostępu i limitów żądań.

W trybie deweloperskim uruchom API w katalogu projektu (`python -m uvicorn backend.app:app --reload --port 8000`), a w drugim terminalu `cd frontend && npm run dev`. Vite przekazuje `/api` do serwera Python.

## Użycie

1. Wpisz nazwę produktu, producenta i stężenie. Aplikacja wyszuka karty i spróbuje odczytać do trzech pierwszych źródeł. Lista źródeł pozwala wybrać inne. Alternatywnie wklej bezpośredni adres PDF/HTML albo wgraj kartę PDF.
2. Sprawdź nazwę, CAS, WE, wzór i masę molową, a w zakładce **Bezpieczeństwo** hasło ostrzegawcze, piktogramy i zwroty H/P/EUH. Program nie uzupełnia brakujących faktów domysłami. Niejednoznaczne dane i braki są sygnalizowane. Wzór i masa molowa nie występują we wszystkich kartach — wtedy należy je uzupełnić ręcznie z właściwego źródła.
3. Wpisz pojemność i numer katalogowy. Kod QR zawiera **dokładnie numer katalogowy**, bez adresu internetowego. Pojemność i numer pozostają zachowane po imporcie kolejnej karty.
4. Porównaj etykietę z aktualną kartą konkretnego produktu i potwierdź sprawdzenie danych. Wybierz **Pobierz PDF** (dokładnie dwie strony 76 × 51 mm) albo **Drukuj**. Przy drukowaniu ustaw skalę 100%, papier 76 × 51 mm, wyłącz marginesy i nagłówki/stopki. Przeglądarkowy zapis PDF może zaokrąglać wymiary; użyj bezpośredniego eksportu, jeśli wymiar musi być dokładny.

PDF jest generowany lokalnie jako obraz około 576 dpi. QR ma biały margines i rozmiar 15 × 15 mm we wzorcowym położeniu. Szkic zapisuje się w localStorage tej przeglądarki, a przycisk z ikoną dokumentu pobiera JSON z danymi i źródłem. Pliki PDF przesłane do API nie są trwale zapisywane.

## Wierność wzorowi

Odtworzono obie strony dokumentu `DJCHEM_wzor_2x76x51_QR.docm`: wymiary, oryginalne logo i zestaw piktogramów, położenie QR oraz układ pól. Kod QR z oryginału zawierał `Oc2`. Dokument Word nie jest uruchamiany i aplikacja nie wykonuje jego makr.

Tekst jest mierzony w przeglądarce i dopasowywany do stałych pól, bez usuwania treści. Skrajnie długa treść, która nie mieści się nawet po zmniejszeniu fontu, blokuje eksport i druk. Minimalna wielkość zwrotów to 2,5 pt, zgodnie z techniczną możliwością dopasowania; czytelność i wymagania dotyczące oznakowania trzeba ocenić osobno. Program nie certyfikuje zgodności etykiety z przepisami.

Wzór używa Times New Roman. Jeżeli font jest dostępny na komputerze, program go użyje; w przeciwnym razie użyje dołączonego Liberation Serif o zgodnych metrykach. Nie przeprowadzono porównania pikselowego z renderem Microsoft Word, więc pełna identyczność typograficzna nie jest potwierdzona. Źródła i licencje grafik/fontów: `frontend/public/template/SOURCES.txt`.

## Wyszukiwanie i ograniczenia

Automatyczne wyszukiwanie korzysta z Bing RSS, a następnie DuckDuckGo HTML. Dostawcy mogą ograniczać automatyczne zapytania lub wymagać CAPTCHA; aplikacja nie omija tych ograniczeń i podaje błąd z możliwością importu PDF. Dostęp do znalezionych kart wymaga także dostępu do domen ich producentów. Nie ma wbudowanej bazy sfabrykowanych kart ani stałych danych podstawianych zamiast nieudanego wyszukiwania.

Odczyt opiera się na sekcjach 1, 2.2, 3 i 9. Formatowanie kart jest różne: tabele, skany, nietypowe nagłówki i rozpoznawanie piktogramów mogą wymagać korekty ręcznej. Angielska karta zachowuje angielskie zwroty; aplikacja nie tworzy niezweryfikowanego tłumaczenia. Dane startowe to wyraźnie oznaczona kopia **etykiety wzorcowej**, a nie karta pobrana z internetu.

W środowisku chmurowym podczas przygotowania aplikacji wyszukiwarki były blokowane przez politykę sieci. Zapisano w projekcie konfiguracji dodatki dla `www.bing.com`, `html.duckduckgo.com`, `www.chempur.pl`, `chempur.pl`, `www.sigmaaldrich.com`, `www.carlroth.com`, `www.stanlab.eu` i `pubchem.ncbi.nlm.nih.gov`. Wymagają zapisania ustawień i publikacji środowiska. Inne znalezione domeny SDS mogą wymagać osobnego dopuszczenia. Sam zapis projektu konfiguracji nie zmienia działającej sieci. Szczegóły ochrony przed odczytem wewnętrznych adresów: `backend/README.md`.

## Weryfikacja

```bash
python -m unittest discover -s backend/tests -v
cd frontend && npm run build
```

Testy przeglądarkowe: `python tests/browser_smoke.py` przy uruchomionej aplikacji, po instalacji `pip install playwright` i Chromium (`playwright install chromium` lub przeglądarka systemowa). Wyniki i zrzuty trafiają do ignorowanego katalogu `artifacts/`.
