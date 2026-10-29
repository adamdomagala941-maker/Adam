# DJCHEM — studio etykiet 1.1

Aplikacja w języku polskim działająca w przeglądarce. Edytor i generator PDF pracują lokalnie w przeglądarce; serwer Python wyszukuje i odczytuje karty charakterystyki. Standardowe wyszukiwanie nie wymaga klucza API. Opcjonalne wyszukiwanie AI korzysta z własnego klucza OpenAI API i jest rozliczane przez dostawcę.

## Aktualizacja z wersji 1.0

Zamknij poprzednie okno serwera (Ctrl+C), rozpakuj nowy ZIP do osobnego katalogu i uruchom `Uruchom.bat` lub `python3 launcher.py`. Launcher instaluje również nowy moduł wyszukiwania `ddgs`. W interfejsie obok opisu powinna być widoczna wersja **v1.1**. Zajęty port powoduje teraz czytelny komunikat zamiast przypadkowego otwarcia starej wersji. Jeżeli stary serwer nadal działa, samo odświeżenie przeglądarki nie aktualizuje backendu.

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

1. Wpisz nazwę produktu, producenta i stężenie. Aplikacja wyszuka karty i spróbuje odczytać do sześciu pierwszych źródeł, także przez linki do kart na stronach produktów. Lista źródeł pozwala wybrać inne. Alternatywnie wklej bezpośredni adres PDF/HTML albo wgraj kartę PDF. W razie niepowodzenia rozwiń **Szczegóły odczytu**, aby zobaczyć przyczynę dla każdego źródła.
2. Sprawdź nazwę, CAS, WE, wzór i masę molową, a w zakładce **Bezpieczeństwo** hasło ostrzegawcze, piktogramy i zwroty H/P/EUH. Program nie uzupełnia brakujących faktów domysłami. Niejednoznaczne dane i braki są sygnalizowane. Wzór i masa molowa nie występują we wszystkich kartach — wtedy należy je uzupełnić ręcznie z właściwego źródła.
3. Wpisz pojemność i numer katalogowy. Kod QR zawiera **dokładnie numer katalogowy**, bez adresu internetowego. Pojemność i numer pozostają zachowane po imporcie kolejnej karty.
4. Porównaj etykietę z aktualną kartą konkretnego produktu i potwierdź sprawdzenie danych. Wybierz **Pobierz PDF** (dokładnie dwie strony 76 × 51 mm) albo **Drukuj**. Przy drukowaniu ustaw skalę 100%, papier 76 × 51 mm, wyłącz marginesy i nagłówki/stopki. Przeglądarkowy zapis PDF może zaokrąglać wymiary; użyj bezpośredniego eksportu, jeśli wymiar musi być dokładny.

PDF jest generowany lokalnie jako obraz około 576 dpi. QR ma biały margines i rozmiar 15 × 15 mm we wzorcowym położeniu. Szkic zapisuje się w localStorage tej przeglądarki, a przycisk z ikoną dokumentu pobiera JSON z danymi i źródłem. Pliki PDF przesłane do API nie są trwale zapisywane.

## Wierność wzorowi

Odtworzono obie strony dokumentu `DJCHEM_wzor_2x76x51_QR.docm`: wymiary, oryginalne logo i zestaw piktogramów, położenie QR oraz układ pól. Kod QR z oryginału zawierał `Oc2`. Dokument Word nie jest uruchamiany i aplikacja nie wykonuje jego makr.

Tekst jest mierzony w przeglądarce i dopasowywany do stałych pól, bez usuwania treści. Skrajnie długa treść, która nie mieści się nawet po zmniejszeniu fontu, blokuje eksport i druk. Minimalna wielkość zwrotów to 2,5 pt, zgodnie z techniczną możliwością dopasowania; czytelność i wymagania dotyczące oznakowania trzeba ocenić osobno. Program nie certyfikuje zgodności etykiety z przepisami.

Wzór używa Times New Roman. Jeżeli font jest dostępny na komputerze, program go użyje; w przeciwnym razie użyje dołączonego Liberation Serif o zgodnych metrykach. Nie przeprowadzono porównania pikselowego z renderem Microsoft Word, więc pełna identyczność typograficzna nie jest potwierdzona. Źródła i licencje grafik/fontów: `frontend/public/template/SOURCES.txt`.

## Wyszukiwanie i ograniczenia

Standardowe wyszukiwanie korzysta z wielosilnikowego DDGS (Brave/Mojeek, następnie Yahoo/DuckDuckGo) oraz zgodnościowych prób Bing RSS i DuckDuckGo HTML. Używa osobnych zapytań po polsku i angielsku. Dostawcy mogą ograniczać automatyczne zapytania lub wymagać CAPTCHA; program tego nie omija. Brak wyników i odmowa dostępu są raportowane oddzielnie. Dostęp do znalezionych kart wymaga również dostępu do domen producentów.

Dla zapytania **Dwuetylohydroksyloamina 85%** program uwzględnia zapisy **dietylohydroksyloamina 85%** oraz **N,N-diethylhydroxylamine 85%**. Stężenie jest zachowywane w wariantach zapytań i rankingu. Jeżeli odczytana nazwa wskazuje inne stężenie, dokument jest odrzucany. Brak stężenia w odczytanej nazwie daje ostrzeżenie — trzeba wtedy porównać skład w źródle. To pomoc w doborze dokumentu, a nie certyfikacja tożsamości produktu.

Wersja 1.1 rozwiązuje ważny brak: wynik będący stroną produktu jest przeszukiwany pod kątem jawnych odnośników „Karta charakterystyki”/„SDS” prowadzących do PDF lub strony karty. Źródłem danych pozostaje faktycznie odczytany dokument. Obsługiwane są również nagłówki `SEKCJA2`, nagłówki numerowane bez słowa SEKCJA, tabele HTML i powtarzane nagłówki kontynuacji. Nie ma wbudowanej bazy sfabrykowanych kart ani danych podstawianych po błędzie wyszukiwania.

### Opcjonalne wyszukiwanie z AI

1. W sekcji wyszukiwania kliknij **Wyszukiwanie i AI**.
2. Dodaj własny klucz z [platform.openai.com/api-keys](https://platform.openai.com/api-keys). Konto API musi mieć aktywne rozliczanie. Abonament ChatGPT nie zastępuje klucza ani środków API.
3. Zaznacz **Włącz wyszukiwanie z AI** i zapisz ustawienia. Samo zapisanie klucza nie włącza płatnych wywołań, dopóki AI nie zostanie zaznaczone.
4. Wpisz nazwę produktu. OpenAI Responses z `web_search` (model `gpt-4.1-mini`) wyszuka źródła. Aplikacja pobiera tylko adresy cytowane w końcowej odpowiedzi i osobno odczytuje z nich dokumenty. Model nie tworzy CAS, zwrotów H/P ani klasyfikacji do etykiety. Przy błędzie AI program próbuje wyszukiwania standardowego i podaje przyczynę.

Klucz jest zapisywany lokalnie w `.local/settings.json`, z ograniczonym dostępem do pliku. Ten katalog jest ignorowany przez Git i wykluczony z paczek tworzonych przez `python tools/package.py`. Klucz nie jest zwracany przez API ani przechowywany w przeglądarkowym szkicu/etykiecie. Można użyć zmiennej `DJCHEM_OPENAI_API_KEY` zamiast klucza w pliku; ta zmienna ma pierwszeństwo. Nadal potrzebne jest jawne włączenie AI. Zmiana ustawień i płatne zapytania są dozwolone tylko z lokalnego adresu aplikacji; zdalne wdrożenia wymagają osobnego uwierzytelniania. Usunięcie klucza z pliku jest dostępne w tym samym oknie ustawień.

Moduł AI wymaga dostępu do `api.openai.com`. Wyszukanie adresu przez AI nie gwarantuje możliwości pobrania dokumentu — producent może wymagać logowania, blokować automat lub publikować skan. W takich przypadkach pozostaje import PDF lub ręczne uzupełnienie danych.

Odczyt opiera się na sekcjach 1, 2.2, 3 i 9. Formatowanie kart jest różne: tabele, skany, nietypowe nagłówki i rozpoznawanie piktogramów mogą wymagać korekty ręcznej. Angielska karta zachowuje angielskie zwroty; aplikacja nie tworzy niezweryfikowanego tłumaczenia. Dane startowe to wyraźnie oznaczona kopia **etykiety wzorcowej**, a nie karta pobrana z internetu.

W środowisku chmurowym podczas przygotowania aplikacji wyszukiwarki i domeny producentów były blokowane przez politykę sieci. Sam zapis projektu konfiguracji nie zmienia działającej sieci; ustawienia wymagają zapisania/publikacji. Dodatkowe domeny silników to `search.brave.com`, `www.mojeek.com`, `search.yahoo.com` i `api.openai.com`, oprócz wcześniejszych Bing/DDG i domen dostawców kart. **Nie potwierdzono rzeczywistego pobrania karty dla dwuetylohydroksyloaminy 85% w tej instancji ani płatnego wywołania AI bez klucza.** Testy automatyczne sprawdzają przepływ wyszukiwania/odczytu na kontrolowanych danych; nie są dowodem znalezienia aktualnej karty danego producenta. Na komputerze użytkownika obowiązuje jego dostęp sieciowy. Szczegóły ochrony przed odczytem wewnętrznych adresów: `backend/README.md`.

## Weryfikacja

```bash
python -m unittest discover -s backend/tests -v
cd frontend && npm run build
```

Testy przeglądarkowe: `python tests/browser_smoke.py` przy uruchomionej aplikacji, po instalacji `pip install playwright` i Chromium (`playwright install chromium` lub przeglądarka systemowa). Wyniki i zrzuty trafiają do ignorowanego katalogu `artifacts/`.

Test interfejsu nowego wyszukiwania: `python tests/browser_search_smoke.py`. Testuje ustawienia AI bez płatnego wywołania oraz odczyt kolejnego źródła na kontrolowanych odpowiedziach. Paczkowanie bez kluczy i zależności: `python tools/package.py`.
