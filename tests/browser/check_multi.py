"""Browser verification against built static files; all GitHub writes are mocked."""
import json
import os
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from threading import Thread
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[2]/'_site'
index=json.loads((root/'data/index.json').read_text())
expected=next(row['count'] for row in index['snapshots'] if row['id']==index['latest'])
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(root)))
Thread(target=server.serve_forever,daemon=True).start()
base='http://127.0.0.1:'+str(server.server_port)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('WHOGA_TEST_CHROMIUM', '/usr/bin/chromium' if Path('/usr/bin/chromium').exists() else p.chromium.executable_path),headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1280,'height':900});errors=[];writes=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def github(route):
        req=route.request
        if req.method=='PUT':
            writes.append(req.post_data_json)
            route.fulfill(json=dict(content=dict(sha='new'),commit=dict(html_url='https://github.com/PoeticEcho/whoga/commit/test')))
        else:route.fulfill(status=404,json=dict(message='not found'))
    page.route('https://api.github.com/**',github)
    page.goto(base+'/');page.wait_for_function("n=>document.querySelector('#kpiGrid').textContent.includes(String(n))",arg=expected)
    page.wait_for_function("document.querySelector('#planMessage').textContent.length>0")
    page.get_by_role('tab',name='단지 관리',exact=True).click()
    page.locator('#complexNumber1').fill('123');page.locator('#complexNumber2').fill('456')
    page.locator('#rotationHours').select_option('6')
    assert '18시간마다' in page.locator('#rotationSummary').inner_text()
    page.locator('#planToken').fill('test-only')
    page.locator('#savePlan').click();page.wait_for_function("document.querySelector('#planMessage').textContent.includes('GitHub에 설정을 저장')")
    assert len(writes)==1 and writes[0]['branch']=='main'
    assert page.locator('#planToken').input_value()==''
    assert not page.evaluate("Object.values(localStorage).some(v=>v.includes('test-only'))")
    page.screenshot(path='/tmp/whoga-multi-manage.png',full_page=True)
    generic=dict(complexNo='123',complexName='테스트아파트',date='2026-10-26',declaredCount=1,count=1,collectedAt='2026-10-26T14:00:00+09:00',source=dict(kind='naver-live'),items=[dict(dong='201동',type='110㎡ (전용84.9)',floor='10/25층',direction='남향',minPrice=9,maxPrice=10,agencyCount=1,floorCat='중층')])
    index=dict(latest='2026-10-26',snapshots=[dict(id='2026-10-26',date='2026-10-26',file='2026-10-26.json',label='2026-10-26',count=1,declaredCount=1,complete=True)])
    def data(route):
        path=route.request.url.rsplit('/',1)[1]
        route.fulfill(json=index if path=='index.json' else {} if path=='status.json' else generic)
    page.route('**/data/complexes/123/*.json',data)
    page.goto(base+'/?complex=123');page.wait_for_function("document.querySelector('#typeCards').textContent.includes('84.9')")
    assert page.locator('#dongFilter option').all_text_contents()==['전체 동','201동']
    page.get_by_role('tab',name='매물 목록').click();assert '201동' in page.locator('#listingText').inner_text()
    page.get_by_role('tab',name='브리핑',exact=True).click();assert '테스트아파트' in page.locator('#briefingText').inner_text()
    page.goto(base+'/?complex=999');page.wait_for_function("document.querySelector('#planMessage').textContent.length>0")
    assert page.locator('#panel-manage').is_visible()
    assert not errors,errors
    print('PASS: existing data, 3-slot form and memory-only token, generic complex filters/report, missing-data management access')
    browser.close()
