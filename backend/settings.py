"""Local, opt-in AI settings; API credentials are never returned publicly.

The optional DJCHEM_OPENAI_API_KEY environment variable overrides a saved key.
A present key alone does not opt in to billable AI calls: ai_enabled defaults
to False. Saving settings performs no network requests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import threading

SETTINGS_PATH = Path(__file__).resolve().parents[1] / ".local" / "settings.json"
KEY_VARIABLE = "DJCHEM_OPENAI_API_KEY"
_LOCK = threading.RLock()


class SettingsError(ValueError):
    """Safe Polish explanation, without a credential or config file contents."""


def _validate_key(value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SettingsError("Klucz OpenAI API musi być tekstem.")
    if allow_empty and value == "":
        return ""
    if not 8 <= len(value) <= 512 or re.search(r"\s", value):
        raise SettingsError("Klucz OpenAI API musi mieć od 8 do 512 znaków i nie może zawierać spacji ani znaków nowej linii.")
    return value


def _environment_key() -> str:
    value = os.environ.get(KEY_VARIABLE, "")
    return _validate_key(value, allow_empty=True)


def _read_saved() -> dict:
    path = Path(SETTINGS_PATH)
    try:
        if path.is_symlink() or path.parent.is_symlink():
            raise SettingsError("Plik lub katalog ustawień jest dowiązaniem. Wybierz zwykły lokalny plik ustawień.")
        saved = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"ai_enabled": False, "openai_api_key": ""}
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, SettingsError):
            raise
        raise SettingsError("Nie można odczytać lokalnych ustawień AI. Sprawdź plik .local/settings.json; program nie nadpisze uszkodzonej konfiguracji.") from exc
    if not isinstance(saved, dict) or not isinstance(saved.get("ai_enabled", False), bool):
        raise SettingsError("Lokalny plik ustawień AI ma nieprawidłowy format. Istniejąca konfiguracja nie została zmieniona.")
    saved.setdefault("ai_enabled", False)
    saved["openai_api_key"] = _validate_key(saved.get("openai_api_key", ""), allow_empty=True)
    return saved


def _public(enabled: bool, file_key: str, environment_key: str) -> dict:
    source = "environment" if environment_key else "file" if file_key else ""
    return {"ai_enabled": enabled, "key_configured": bool(source), "key_source": source}


def load_settings() -> dict:
    """Internal settings. Caller must never return this object through an API."""
    with _LOCK:
        saved = _read_saved()
        return {"ai_enabled": saved["ai_enabled"], "openai_api_key": _environment_key() or saved["openai_api_key"]}


def public_settings() -> dict:
    """Return only opt-in state and credential presence, never its value."""
    with _LOCK:
        saved = _read_saved()
        return _public(saved["ai_enabled"], saved["openai_api_key"], _environment_key())


def _write_atomic(saved: dict) -> None:
    path = Path(SETTINGS_PATH)
    temporary = None
    descriptor = None
    try:
        if path.is_symlink() or path.parent.is_symlink():
            raise SettingsError("Ustawienia AI muszą być zwykłym plikiem w lokalnym katalogu, bez dowiązań.")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            path.parent.chmod(0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=path.parent)
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = None
            json.dump(saved, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except SettingsError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise SettingsError("Nie udało się bezpiecznie zapisać ustawień AI. Sprawdź uprawnienia katalogu .local i wolne miejsce; poprzedni plik pozostał zachowany.") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass


def save_settings(ai_enabled: bool, api_key: str | None = None, clear_key: bool = False) -> dict:
    """Persist an explicit opt-in. None/empty key preserves the existing key.

    clear_key is required to remove a saved credential. Environment credentials
    must be removed from the process environment rather than through this API.
    Every validation runs before writing, so errors preserve the existing file.
    """
    if not isinstance(ai_enabled, bool) or not isinstance(clear_key, bool):
        raise SettingsError("Opcje włączenia AI i usunięcia klucza muszą mieć wartość tak albo nie.")
    if api_key is not None and not isinstance(api_key, str):
        raise SettingsError("Klucz OpenAI API musi być tekstem.")
    if clear_key and api_key:
        raise SettingsError("Nie można jednocześnie usuwać i zastępować klucza API.")
    replacement = _validate_key(api_key) if api_key else None
    with _LOCK:
        saved = _read_saved()
        environment_key = _environment_key()
        if clear_key and environment_key:
            raise SettingsError("Klucz jest ustawiony w zmiennej DJCHEM_OPENAI_API_KEY. Usuń tę zmienną w środowisku uruchomienia; aplikacja nie może jej wyczyścić.")
        file_key = "" if clear_key else replacement if replacement is not None else saved["openai_api_key"]
        if ai_enabled and not (environment_key or file_key):
            raise SettingsError("Przed włączeniem wyszukiwania AI dodaj klucz OpenAI API. Sam abonament ChatGPT nie zastępuje klucza API.")
        saved.update(ai_enabled=ai_enabled, openai_api_key=file_key)
        _write_atomic(saved)
        return _public(ai_enabled, file_key, environment_key)
