"""Launch the packaged browser app on Windows/macOS/Linux with Python 3.11+."""
from pathlib import Path
import http.client
import os
import subprocess
import sys
import threading
import time
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent


def open_when_ready(port):
    for _ in range(100):
        try:
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=1)
            connection.request('GET', '/api/health')
            ready = connection.getresponse().status == 200
            connection.close()
            if ready:
                webbrowser.open(f'http://127.0.0.1:{port}')
                return
        except OSError:
            pass
        time.sleep(.2)


def main():
    os.chdir(ROOT)
    if sys.version_info < (3, 11):
        raise SystemExit('Wymagany Python 3.11 lub nowszy.')
    if not (ROOT / 'frontend/dist/index.html').exists():
        raise SystemExit('Brak frontend/dist. Pobierz pelny ZIP albo wykonaj npm ci && npm run build w frontend/.')
    if '--serve' in sys.argv:
        import uvicorn
        port = int(os.environ.get('PORT', '8000'))
        threading.Thread(target=open_when_ready, args=(port,), daemon=True).start()
        print('DJCHEM: pozostaw to okno otwarte. Ctrl+C zatrzymuje program.', flush=True)
        uvicorn.run('backend.app:app', host='127.0.0.1', port=port)
        return
    folder = ROOT / '.venv'
    python = folder / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('Przygotowywanie srodowiska Python (pierwsze uruchomienie)...', flush=True)
        venv.EnvBuilder(with_pip=True).create(folder)
    subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'backend/requirements.txt'], check=True)
    raise SystemExit(subprocess.call([str(python), str(Path(__file__).resolve()), '--serve']))


if __name__ == '__main__':
    main()
