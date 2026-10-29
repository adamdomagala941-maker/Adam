"""End-to-end checks against a running local app, using real Chromium and API.

Run from project root: python tests/browser_smoke.py
Optional env: APP_URL, CHROMIUM_PATH.
Fixtures are deliberately synthetic and never presented as a real supplier SDS.
"""
import asyncio
import json
import os
from pathlib import Path
import sys

from playwright.async_api import async_playwright
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.tests.test_backend import SDS, pdf_fixture


async def main():
    artifacts = ROOT / 'artifacts'
    artifacts.mkdir(exist_ok=True)
    base = os.environ.get('APP_URL', 'http://127.0.0.1:8000')
    async with async_playwright() as p:
        args = {'headless': True, 'args': ['--no-sandbox']}
        executable = os.environ.get('CHROMIUM_PATH')
        if not executable and Path('/usr/bin/chromium').exists():
            executable = '/usr/bin/chromium'
        if executable:
            args['executable_path'] = executable
        browser = await p.chromium.launch(**args)
        page = await browser.new_page(viewport={'width':1440, 'height':1100})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(base)
        await page.locator('.label-qr').wait_for()
        await page.evaluate('document.fonts.ready')
        assert await page.locator('.chemical-label').count() == 2
        assert not await page.get_by_role('button', name='Pobierz PDF', exact=True).is_enabled()
        await page.get_by_role('checkbox').check()
        await page.get_by_role('button', name='Pobierz PDF', exact=True).wait_for(state='visible')
        async with page.expect_download() as download_event:
            await page.get_by_role('button', name='Pobierz PDF', exact=True).click()
        download = await download_event.value
        pdf_path = artifacts / 'etykieta-wzor-dokladny.pdf'
        await download.save_as(pdf_path)
        pdf = PdfReader(pdf_path)
        assert len(pdf.pages) == 2, len(pdf.pages)
        for pdf_page in pdf.pages:
            assert abs(float(pdf_page.mediabox.width) * 25.4 / 72 - 76) < .001
            assert abs(float(pdf_page.mediabox.height) * 25.4 / 72 - 51) < .001

        # QR is regenerated from the field, and review is reset on any edit.
        previous_qr = await page.locator('.label-qr').get_attribute('src')
        await page.get_by_text('Numer katalogowy', exact=True).locator('..').locator('input').fill('TEST-QR-2026')
        await page.wait_for_function("document.querySelector('.label-qr')?.alt === 'Kod QR: TEST-QR-2026'")
        assert previous_qr != await page.locator('.label-qr').get_attribute('src')
        assert not await page.get_by_role('checkbox').is_checked()
        await page.reload()
        assert await page.get_by_text('Numer katalogowy', exact=True).locator('..').locator('input').input_value() == 'TEST-QR-2026'

        # Actual PDF upload runs through the backend parser, without mocked API.
        await page.locator('input[type=file]').set_input_files({'name':'synthetic-sds-test.pdf','mimeType':'application/pdf','buffer':pdf_fixture(SDS)})
        await page.get_by_text('Dane odczytane z dokumentu', exact=True).wait_for()
        assert await page.get_by_text('Numer CAS', exact=True).locator('..').locator('input').input_value() == '78-83-1'
        assert await page.get_by_text('Numer katalogowy', exact=True).locator('..').locator('input').input_value() == 'TEST-QR-2026'
        assert await page.locator('.label-statements').inner_text()

        await page.get_by_role('tab', name='Bezpieczeństwo').click()
        hazards = page.get_by_text('Zwroty zagrożenia H', exact=True).locator('..').locator('textarea')
        original = await hazards.input_value()
        assert 'H226' in original and 'H999' not in original
        await hazards.fill(('H226 Bardzo długa treść testowa. ' * 55))
        await page.wait_for_timeout(200)
        size = float(await page.locator('.label-statements').get_attribute('data-font-size'))
        assert size < 5, size
        await hazards.fill('H226 Bardzo długa treść testowa. ' * 3000)
        await page.wait_for_timeout(200)
        assert 'nie mieści' in await page.locator('.fit-status').inner_text()
        await page.get_by_role('checkbox').check()
        assert not await page.get_by_role('button', name='Pobierz PDF', exact=True).is_enabled()
        await hazards.fill(original)
        await page.wait_for_timeout(200)

        # Network failure stays a clear error; it never replaces the label with fake data.
        await page.locator('#search-input').fill('aceton Chempur')
        await page.get_by_role('button', name='Szukaj', exact=True).click()
        await page.wait_for_function("!document.querySelector('.busy-message')", timeout=90000)
        # Public providers may be allowed on other machines, hence verify structure rather than force failure.
        if await page.get_by_role('alert').count():
            assert (await page.get_by_role('alert').inner_text()).strip()

        # Screenshot template state, desktop and phone; no horizontal document overflow.
        page.on('dialog', lambda dialog: dialog.accept())
        await page.get_by_role('button', name='Wczytaj wzór').click()
        await page.get_by_role('tab', name='Identyfikacja produktu').click()
        await page.screenshot(path=artifacts/'studio-desktop.png', full_page=True)
        await page.set_viewport_size({'width':390,'height':844})
        await page.wait_for_timeout(100)
        width_before = await page.locator('.chemical-label').first.evaluate('(e)=>e.getBoundingClientRect().width')
        await page.get_by_role('button', name='Powiększ podgląd').click()
        width_after = await page.locator('.chemical-label').first.evaluate('(e)=>e.getBoundingClientRect().width')
        assert width_after > width_before
        await page.get_by_role('button', name='Pomniejsz podgląd').click()
        await page.screenshot(path=artifacts/'studio-mobile.png', full_page=True)
        assert await page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        assert not errors, errors
        await browser.close()
    print(json.dumps({'result':'PASS', 'checks':['two label pages','exact PDF size','QR regeneration','review reset','local draft restore','real PDF upload and parsing','font auto fit','overflow blocks export','search error handling','mobile layout','no browser errors']},ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
