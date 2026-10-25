"""Real sequential browsers and mobile emulation; all page traffic is intercepted."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, '/app/nas')
from playwright.sync_api import sync_playwright
from browser_control import desktop_connected
from comparison import compare
from version import build_info

folder = Path('/output/comparison-fixture')
folder.mkdir(exist_ok=True)
status = dict(runId='c'*32, build=build_info(), mode='compare', publicationEligible=False)


def fixture(context, page):
    def route(request):
        if request.request.resource_type != 'document':
            request.fulfill(status=500 if 'nlog.naver.com' in request.request.url else 200,
                            content_type='application/json', body='{}')
            return
        request.fulfill(status=200, content_type='text/html; charset=utf-8', body='''<!doctype html>
        <meta name="viewport" content="width=device-width,initial-scale=1"><title>Comparison fixture</title>
        <script>
          const warm = sessionStorage.getItem('seen'); sessionStorage.setItem('seen','yes');
          document.addEventListener('DOMContentLoaded', () => {
            document.body.innerHTML = warm ? '<h3>매물 122</h3><ul class="ComplexArticleTab_test__article"><li><a href="/articles/123">매매 7억</a></li></ul>' : '<h3>매물 0</h3>';
            fetch('/front-api/v1/complex/auth/mount'); fetch('/front-api/v1/complex/article/list');
            fetch('https://nlog.naver.com/n', {method:'POST'}).catch(()=>{});
          });
        </script><body></body>''')
    context.route('**/*', route)


with sync_playwright() as pw:
    report = compare(pw, 'https://fin.land.naver.com/complexes/140635', folder, status,
                     lambda phase: print(phase, flush=True), seconds=1, fixture=fixture)
    assert len(report['conditions']) == 6, report
    for condition in report['conditions']:
        assert condition['outcome'] == 'cards-visible', condition
        first, reload = condition['attempts']
        assert not first['cardsVisible'] and reload['cardsVisible'], condition
        assert reload['navigation'] == 'reload'
        assert reload['listing']['count'] == 122
        assert reload['listing']['visibleCards'] == 1
        env = reload['page']['environment']
        assert env['viewport']['width'] == (1440 if condition['profile'] == 'desktop' else 400), env
        assert env['timeZone'] == 'Asia/Seoul' and env['language'] == 'ko-KR', env
        assert env['languages'] == ['ko-KR', 'ko', 'en-US', 'en'], env
        assert env['mobile'] == (condition['profile'] == 'android'), env
        assert env['maxTouchPoints'] > 0 if condition['profile'] == 'android' else env['maxTouchPoints'] == 0
        if condition['profile'] == 'android':
            assert env['userAgentData']['platform'] == 'Android', env
        else:
            assert env['userAgentData']['platform'] == 'Linux' and env['userAgentData']['brands'], env
        process = reload['resources']['browser']
        assert not process['headless'] and not process['sharedMemoryDisabled'], process
        # Playwright 1.63 uses a debugging pipe; do not assume an automation flag.
        assert process['debuggingPipe'] == (condition['launcher'] == 'playwright'), process
        assert reload['resources']['memory']['limitBytes'] == 3 * 1024**3
        assert any(e.get('status') == 200 and '/auth/mount' in e.get('url', '') for e in reload['duringRun']['events'])
        assert not reload['assessment']['resourceFailureDuringRun']
    assert status['diagnosticsPath'] and (folder / 'diagnostics.json').exists()
    assert len(list(folder.glob('*.png'))) == 12
    deadline = time.monotonic() + 30
    while not desktop_connected():
        assert time.monotonic() < deadline, 'Persistent desktop was not restored'
        time.sleep(.2)
    restored = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    assert restored.contexts[0].pages[0].title() == 'WhoGa NAS 브라우저 준비 완료' or 'WhoGa NAS' in restored.contexts[0].pages[0].title()
print('PASS: six fresh headed conditions, matching mobile UA/Client Hints, warm reload, saved evidence and restored desktop', flush=True)
