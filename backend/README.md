Backend uruchamiany z katalogu głównego projektu:

```sh
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
python -m unittest discover -s backend/tests -v
```

`GET /api/search?q=...` wyszukuje karty w Bing RSS i DuckDuckGo. Wymaga dostępu do `www.bing.com` i `html.duckduckgo.com`; serwery mogą wymagać CAPTCHA lub blokować automatyczne zapytania. Brak dostępu daje HTTP 503 z opisem, nie pozorne puste wyniki. `POST /api/extract` przyjmuje JSON `{url, expected_name?}`. `POST /api/upload` przyjmuje pole multipart `file` z PDF/TXT. Maksymalnie 15 MB, 120 stron PDF. Nie wykonuje dokumentów Word, makr ani skryptów ze stron.

Parser odczytuje sekcję 2.2 (lub sekcję 2 z ostrzeżeniem), identyfikatory z sekcji 1 i 3 oraz wzór/masę, jeśli są jawnie podane. Piktogramy odczytuje z kodów GHS w tekście. Jeżeli ich nie ma, PDF jest sprawdzany wizualnie pod kątem standardowych czerwonych piktogramów w sekcji 2.2 (ostrożne dopasowanie szablonów, do 3 stron). Nierozpoznane, monochromatyczne lub słabo czytelne symbole trzeba wskazać ręcznie; nie są zgadywane na podstawie kodów H. Wynik graficzny jest jawnie oznaczony i wymaga porównania z oryginałem. Przy kilku numerach CAS składników nie wybiera dowolnego numeru. Brakujące dane pozostają puste. Oryginalny tekst i sekcje dowodowe są w odpowiedzi `source.evidence`. Odczyt nie zastępuje sprawdzenia karty konkretnego produktu/stężenia, daty i elementów oznakowania.

Pobieranie działa przez odziedziczone proxy i z włączoną weryfikacją TLS. Adresy lokalne, jawne prywatne IP, dane logowania i porty inne niż 80/443 są odrzucane; każdy cel przekierowania jest sprawdzany ponownie. Przy dostępnej lokalnej usłudze DNS wszystkie odpowiedzi DNS muszą być globalnymi adresami IP.

W zarządzanym środowisku Codex z `/etc/codex/network-policy.json` w wersji 1, polityką `restricted` i odziedziczonym dokładnie `http://proxy:8080`, lokalny DNS może być celowo niedostępny. Tylko dla domen **jawnie** wymienionych w tej polityce można wówczas zlecić rozwiązywanie adresu zaufanemu proxy platformy, które egzekwuje listę dozwolonych celów. Nie ma tego wyjątku dla dowolnego proxy, polityki unrestricted, wildcardów ani nieznanych domen. W takim środowisku po wpisaniu nowego adresu karty może być konieczne dodanie domeny dostawcy w ustawieniach sieci. W razie braku dostępu nadal działa wczytanie pliku.

Po budowie frontendu w `frontend/dist` serwer automatycznie udostępnia aplikację pod `/`. Podczas rozwoju Vite przekazuje `/api` do portu 8000.
