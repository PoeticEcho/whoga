"""Docker integration: local fixtures only; no real Naver traffic or GitHub writes."""
import base64
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8899'
AUTH = 'Basic ' + base64.b64encode(('admin:' + os.environ['DASHBOARD_PASSWORD']).encode()).decode()
TARGET = 'https://fin.land.naver.com/complexes/140635'


def api(path, body=None):
    headers = {'Authorization': AUTH}
    if body is not None:
        headers.update({'Content-Type': 'application/json', 'X-Whoga-Request': '1'})
    with urlopen(Request(BASE + path, headers=headers, data=json.dumps(body).encode() if body is not None else None), timeout=5) as response:
        return json.load(response)


def fixture(kind):
    prefix = '<html lang="ko"><title>WhoGa fixture</title><section id="complex_detail"><h3>수성범어더블유</h3><button>매매 1</button><button id="거래유형">매매</button><a role="tab" href="/complexes/140635?tab=article">매물</a>'
    if kind == 'csp':
        return prefix + '<p>로딩중</p></section></html>'
    if kind == 'error':
        return '<html><title>500 Internal Server Error</title><h1>서비스 오류</h1></html>'
    return prefix + '''<h4>매물 1</h4><ul class="ComplexArticleTab_fixture__article"><li><div>
      <a class="__link" href="/articles/1234567890"><span class="__name">수성범어더블유</span></a>
      <span class="__price">매매 10억</span><span class="__item-summary">오피스텔</span>
      <span class="__item-summary">100/84㎡</span><span class="__item-summary">20/59층</span>
      <span class="__item-summary">남향</span><span data-sentry-component="PropertyBadgeList">확인매물 2026.10.25</span>
      </div></li></ul></section></html>'''


with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    context = browser.contexts[0]
    page = context.pages[0]
    kind = 'success'

    def route(request):
        # Every browser request is intercepted; TARGET is an entirely local fixture.
        if request.request.resource_type == 'document':
            headers = {'Content-Type': 'text/html; charset=utf-8'}
            if kind == 'csp':
                headers['Content-Security-Policy'] = "script-src 'none'"
            request.fulfill(status=500 if kind == 'error' else 200, headers=headers, body=fixture(kind))
        else:
            request.fulfill(status=200, content_type='text/javascript', body='/* local fixture */')

    context.route('**/*', route)

    def wait_for(test, seconds=50):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            result = test()
            if result:
                return result
            page.wait_for_timeout(100)
        raise AssertionError('Local fixture worker did not reach the expected state')

    def finished():
        state = api('/api/status')['state']
        return state if not state['running'] else None

    def execute(mode):
        api('/api/run', {'mode': mode})
        return wait_for(finished)

    build = api('/api/status')['build']
    assert build['version'] == '2.4' and len(build['sourceFingerprint']) == 64
    assert build['sourceCommit'] == os.environ['WHOGA_EXPECT_SOURCE_COMMIT']

    # Regression: "매물 1" has no "개" suffix. Exercise the real collector and normalizer.
    page.goto(TARGET)
    success = execute('probe')
    assert success['result'] == 'probe-passed', success
    assert success['lastResult']['probe']['cards'] == 1
    assert success['lastResult']['assessment']['pageState'] == 'listing-cards-visible'
    resources = success['lastResult']['resources']
    assert resources['memory']['currentBytes'] > 0
    assert resources['memory']['limitBytes'] == 3 * 1024**3
    assert resources['filesystems']['sharedMemory']['totalBytes'] == 512 * 1024**2
    assert resources['filesystems']['tmp']['availableBytes'] > 0
    assert resources['browser']['sharedMemoryDisabled'] is False
    assert resources['browser']['headless'] is False

    # browse stops at document response; errors occurring afterward remain in browser history.
    kind = 'csp'
    opened = execute('browse')
    assert opened['result'] == 'page-opened'

    def blocked_script():
        page.evaluate("() => { const s=document.createElement('script'); s.src='/fixture-blocked.js'; document.head.append(s); }")

    blocked_script()
    page.wait_for_timeout(1600)
    history = json.loads(Path('/output/browser-diagnostics.json').read_text())
    assert any(e['kind'] == 'browser-blocked' and e.get('blockedReason') == 'csp' for e in history['events'])

    # This fixture has the complex and sale filter, but deliberately no list heading.
    api('/api/run', {'mode': 'probe'})
    wait_for(lambda: 'probe:list-count' in Path('/output/current.log').read_text(), seconds=20)
    blocked_script()
    page.evaluate("() => { setTimeout(() => { throw Error('fixture-javascript-error'); }, 0); }")
    failed = wait_for(finished)
    result = failed['lastResult']
    assert failed['result'] == 'failed' and result['failedPhase'] == 'probe:list-count', failed
    assert result['assessment']['pageState'] == 'loading-or-empty-list'
    assert result['assessment']['cspBlockedDuringRun']
    assert result['assessment']['javascriptErrorDuringRun']
    report = api(failed['diagnosticLinks']['report'])
    assert report['page']['title'] == 'WhoGa fixture'
    assert report['page']['saleFilter'] == '매매'
    assert report['browserHistory']['events']
    assert any(e.get('blockedReason') == 'csp' for e in report['duringRun']['events'])
    assert any(e.get('csp') == "script-src 'none'" for e in report['browserHistory']['events'])
    with urlopen(Request(BASE + failed['diagnosticLinks']['screenshot'], headers={'Authorization': AUTH}), timeout=5) as response:
        assert response.read(8) == b'\x89PNG\r\n\x1a\n'
    assert not (Path('/output/jobs') / failed['jobId'] / 'runs' / result['runId'] / 'full.json').exists()

    kind = 'error'
    error_page = execute('browse')['lastResult']
    assert error_page['status'] == 'failed' and error_page['documentStatus'] == 500
    assert error_page['assessment']['pageState'] == 'error-screen'
    context.unroute('**/*', route)
    print('PASS: real probe, failure diagnostics, CSP and JS errors, post-browse history, HTTP 500, source commit, measured cgroup/tmp/shm and headed browser using /dev/shm')
