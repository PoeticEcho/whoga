"""Keep a visible browser alive; collection clients attach over local CDP."""
from playwright.sync_api import sync_playwright
from diagnostics import BrowserEvents
from browser_control import READY, comparison_active
from browser_runtime import bootstrap, configure, launch
from pathlib import Path
import json
import tempfile
import time


def lifecycle(phase):
    print(json.dumps({'component': 'desktop', 'phase': phase}), flush=True)


def main():
    READY.unlink(missing_ok=True)
    while True:
        while comparison_active():
            time.sleep(.2)
        desktop()


def desktop():
    lifecycle('driver-start')
    # A comparison closes the default browser deliberately. Reusing its profile
    # can restore old tabs and stall CDP attachment before emulation is applied.
    # Workers share this browser until it closes; only a new desktop gets a profile.
    with tempfile.TemporaryDirectory(prefix='whoga-native-') as directory, sync_playwright() as pw:
        # NAS evidence: this native launcher loaded the real complex and listing API.
        with launch(pw, 'native', Path(directory), port=9222) as (browser, context):
            lifecycle('browser-connected')
            page = context.pages[0] if context.pages else context.new_page()
            for extra in context.pages[1:]:
                extra.close()
            bootstrap(page)
            lifecycle('bootstrap-loaded')
            configure(page, 'desktop', 1440, 900, browser.version)
            events = BrowserEvents(context)
            page.set_content('<html lang="ko"><meta charset="utf-8"><title>WhoGa NAS 브라우저</title>'
                             '<body style="font:24px sans-serif;padding:60px;background:#edf3ed;color:#244b36">'
                             '<h1>WhoGa 브라우저 준비 완료</h1><p>관리 화면에서 원문 열기 또는 수집을 시작하세요.</p>'
                             '<p>이 창이 실제 수집에 사용됩니다.</p></body></html>')
            page.bring_to_front()
            READY.touch()
            lifecycle('ready')
            try:
                while context.pages and not comparison_active():
                    context.pages[0].wait_for_timeout(1000)
                    events.persist('/output/browser-diagnostics.json')
            finally:
                READY.unlink(missing_ok=True)
                lifecycle('browser-stopping')
        lifecycle('browser-stopped')
    lifecycle('driver-stopped')

if __name__ == '__main__':
    main()
