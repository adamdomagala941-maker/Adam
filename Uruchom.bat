@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 launcher.py
) else (
    python launcher.py
)
if errorlevel 1 (
    echo.
    echo Uruchomienie nie powiodlo sie. Sprawdz komunikat powyzej.
    echo Wymagany jest Python 3.11 lub nowszy z python.org.
    pause
)
