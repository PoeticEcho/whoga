"""Exercise native desktop -> lazy listing -> expanded groups -> validated JSON locally."""
import base64
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8899'
TARGET = 'https://fin.land.naver.com/complexes/140635'
AUTH = 'Basic ' + base64.b64encode(('admin:' + os.environ['DASHBOARD_PASSWORD']).encode()).decode()


def api(path, body=None):
    headers = {'Authorization': AUTH}
    if body is not None:
        headers.update({'Content-Type': 'application/json', 'X-Whoga-Request': '1'})
    with urlopen(Request(BASE + path, headers=headers,
                         data=json.dumps(body).encode() if body is not None else None), timeout=5) as response:
        return json.load(response)


HTML = '''<!doctype html><meta charset="utf-8"><title>Native full collection fixture</title>
<section id="complex_detail" style="height:500px;overflow:auto;width:550px">
<h3>수성범어더블유</h3><button onclick="throw Error('already selected sale was clicked')">매매 8</button>
<button id="거래유형">매매</button><a role="tab" href="/complexes/140635?tab=article">매물</a>
<h4>매물<strong id="count">0</strong><span>개</span><button>도움말 보기</button></h4>
<ul class="ComplexArticleTab_fixture__article"></ul></section>
<script>
const list = document.querySelector('ul'), panel = document.querySelector('#complex_detail');
let added=0, pending=false;
function append() {
  for(let n=0;n<2 && added<8;n++,added++) {
    const li=document.createElement('li'); li.style.minHeight='230px';
    li.innerHTML=`<div><a class="__link" href="/articles/${1000+added}"><span class="__name">수성범어더블유</span></a>
      <span class="__price">매매 10억</span><span class="__item-summary">오피스텔</span>
      <span class="__item-summary">100/84㎡</span><span class="__item-summary">20/59층</span>
      <span class="__item-summary">남향</span><span data-sentry-component="PropertyBadgeList">확인매물 2026.10.25</span></div>`;
    if(added===0) {
      const button=document.createElement('button'); button.textContent='매물목록 펼치기';
      li.firstChild.insertAdjacentHTML('beforeend','<span class="__text-more">중개사 2곳에서 등록했어요</span>');
      button.onclick=()=>{
        if(button.textContent==='매물목록 접기') {
          li.querySelectorAll('[data-sentry-component="ArticleCardSub"]').forEach(el=>el.remove());
          button.textContent='매물목록 펼치기';return;
        }
        setTimeout(()=>{for(const id of [2001,2002]) li.insertAdjacentHTML('beforeend',`<div data-sentry-component="ArticleCardSub"><a class="__link" href="/articles/${id}">개별 매물</a><span class="__price">매매 10억</span><span data-sentry-component="PropertyBadgeList">확인매물 2026.10.25</span></div>`);
          button.textContent='매물목록 접기';},80);
      };
      li.append(button);
    }
    list.append(li);
  }
}
append();
panel.addEventListener('scroll',()=>{
  if(!pending && added<8 && panel.scrollTop+panel.clientHeight>=panel.scrollHeight-30) {
    pending=true;setTimeout(()=>{append();pending=false;},80);
  }
});
setTimeout(()=>document.querySelector('#count').textContent='8',1800);
</script>'''

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    context = browser.contexts[0]
    page = context.pages[0]
    documents = []

    def route(request):
        if request.request.resource_type != 'document':
            request.fulfill(status=200, body='')
        else:
            documents.append(request.request.url)
            if urlsplit(request.request.url).path.startswith('/complexes/'):
                request.fulfill(status=307, headers={'Location': 'https://fin.land.naver.com/map?layer=fixture'})
            else:
                request.fulfill(status=200, content_type='text/html; charset=utf-8', body=HTML)

    context.route('**/*', route)
    page.goto(TARGET)
    api('/api/run', {'mode': 'full'})
    deadline = time.monotonic() + 120
    while True:
        state = api('/api/status')['state']
        if not state['running']:
            break
        assert time.monotonic() < deadline, 'Full collection timed out'
        page.wait_for_timeout(100)
    assert state['result'] == 'full-passed', state
    assert len(documents) == 2, ('Unnecessary map navigation lost the loaded list', documents)
    run = state['lastResult']['runId']
    payload = json.loads((Path('/output/jobs') / state['jobId'] / 'runs' / run / 'full.json').read_text())
    assert payload['displayedCardCount'] == payload['collectedCardCount'] == 8, payload
    assert payload['articleCount'] == 9 and len({a['articleNo'] for a in payload['articles']}) == 9
    assert payload['cards'][0]['articleNos'] == ['2001','2002']
    assert len(payload['observedCardCounts']) > 1, payload['observedCardCounts']
    assert payload['target']['sourceUrl'] == TARGET and not payload['publicationEligible']
    report = api(state['diagnosticLinks']['report'])
    assert report['page']['environment']['webdriver'] is False
    assert report['resources']['browser']['debuggingPipe'] is False
    assert not any(e['kind'] == 'javascript-error' for e in report['duringRun']['events'])
    context.unroute('**/*', route)
print('PASS: native full collection, lazy pagination, expanded group members, preserved map session and validated JSON', flush=True)
