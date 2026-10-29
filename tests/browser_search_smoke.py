"""UI regression for search/AI configuration; no paid AI or real SDS claims."""
import asyncio
import json
import os
from pathlib import Path
import sys

from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.parser import parse_sds
from backend.tests.test_backend import SDS


async def main():
    base=os.environ.get('APP_URL','http://127.0.0.1:8000')
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1440,'height':1100})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        await page.goto(base)
        await page.get_by_role('button',name='Wyszukiwanie i AI').click()
        dialog=page.get_by_role('dialog')
        await dialog.get_by_text('Włącz wyszukiwanie z AI',exact=True).wait_for()
        await dialog.get_by_role('checkbox').check()
        await dialog.get_by_role('button',name='Zapisz ustawienia').click()
        await dialog.get_by_role('alert').wait_for()
        assert 'klucz' in await dialog.get_by_role('alert').inner_text()
        assert 'Abonament ChatGPT' in await dialog.inner_text()
        await dialog.get_by_role('button',name='Zamknij ustawienia').click()

        # Only browser-bound provider responses are controlled. This test does
        # not assert that a current manufacturer SDS was found on the internet.
        candidates=[{'title':'Dwuetylohydroksyloamina 85% — strona produktu','url':'https://supplier.example/product','provider':'Test provider'},
                    {'title':'Dietylohydroksyloamina 85% — karta','url':'https://supplier.example/card.pdf','provider':'Test provider'}]
        async def search(route):
            await route.fulfill(json={'results':candidates,'warnings':[]})
        await page.route('**/api/search?*',search)
        fixture=parse_sds(SDS.replace('ALKOHOL IZOBUTYLOWY','N,N-DIETYLOHYDROKSYLOAMINA 85%'),url=candidates[1]['url'],title='SYNTHETIC UI TEST, NOT A MANUFACTURER SDS')
        visited=[]
        async def extract(route):
            url=route.request.post_data_json['url']
            visited.append(url)
            if url==candidates[0]['url']:
                await route.fulfill(status=422,json={'detail':'Test: niedostępny dokument'})
            else:
                await route.fulfill(json=fixture)
        await page.route('**/api/extract',extract)
        await page.locator('#search-input').fill('Dwuetylohydroksyloamina 85%')
        await page.get_by_role('button',name='Szukaj',exact=True).click()
        await page.get_by_text('Dane odczytane z dokumentu',exact=True).wait_for()
        assert visited==[candidate['url'] for candidate in candidates]
        assert await page.get_by_text('Nazwa na etykiecie',exact=True).locator('..').locator('input').input_value()=='N,N-DIETYLOHYDROKSYLOAMINA 85%'
        assert not await page.get_by_role('checkbox').is_checked()

        # Failed documents retain a per-source reason, and never replace data.
        await page.unroute('**/api/extract',extract)
        async def fail_extract(route):
            await route.fulfill(status=422,json={'detail':'Test: nie rozpoznano dokumentu źródłowego'})
        await page.route('**/api/extract',fail_extract)
        await page.get_by_role('button',name='Szukaj',exact=True).click()
        await page.get_by_role('alert').wait_for()
        await page.get_by_text('Szczegóły odczytu (2)',exact=True).click()
        assert await page.locator('.search-attempts li').count()==2
        assert 'nie rozpoznano' in await page.locator('.search-attempts').inner_text()
        assert not errors,errors
        await page.get_by_role('button',name='Wyszukiwanie i AI').click()
        (ROOT/'artifacts').mkdir(exist_ok=True)
        await page.screenshot(path=ROOT/'artifacts/search-settings-v1.1.png',full_page=True)
        await browser.close()
    print(json.dumps({'result':'PASS','checks':['AI opt-in requires key','API billing explanation visible','tries next source after parse failure','85% formulation preserved in UI','review resets','per-source errors visible','no browser errors'],'external_search':'mocked; no paid AI request'},ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(main())
