"""Build the portable ZIP, excluding dependencies, local secrets and old ZIPs."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'download'/'DJCHEM-studio.zip'
EXCLUDED={'.git','.venv','node_modules','__pycache__','artifacts','.pytest_cache','.local','download'}


def package():
    OUTPUT.parent.mkdir(exist_ok=True)
    with ZipFile(OUTPUT,'w',ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob('*')):
            relative=path.relative_to(ROOT)
            if any(part in EXCLUDED for part in relative.parts) or path.is_symlink() or not path.is_file():
                continue
            if path.name.endswith(('.pyc','.tsbuildinfo')) or path.name=='.env' or path.name.startswith('.env.'):
                continue
            archive.write(path,Path('DJCHEM-studio')/relative)
        sample=ROOT/'artifacts'/'etykieta-wzor-dokladny.pdf'
        if sample.is_file():
            archive.write(sample,'DJCHEM-studio/Przyklad-etykiety.pdf')
    with ZipFile(OUTPUT) as archive:
        assert archive.testzip() is None
        assert 'DJCHEM-studio/frontend/dist/index.html' in archive.namelist()
        assert not any('/.local/' in name for name in archive.namelist())
    print(f'ZIP ready: {OUTPUT} ({OUTPUT.stat().st_size} bytes)')


if __name__=='__main__':
    package()
