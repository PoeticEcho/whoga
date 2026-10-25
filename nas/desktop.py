"""Keep a visible browser alive; collection clients attach over local CDP."""
from playwright.sync_api import sync_playwright
from diagnostics import BrowserEvents


def main():
    with sync_playwright() as pw:
        # Retain the supplied DS420+ compatibility setting. No host privileges.
        context = pw.chromium.launch_persistent_context(
            '/tmp/whoga-browser-profile', headless=False, chromium_sandbox=False,
            # Use the container's dedicated /dev/shm instead of the profile's /tmp.
            ignore_default_args=['--disable-dev-shm-usage'],
            locale='ko-KR', timezone_id='Asia/Seoul', viewport={'width': 1440, 'height': 900},
            args=['--remote-debugging-address=127.0.0.1', '--remote-debugging-port=9222',
                  '--window-size=1440,1000', '--start-maximized'])
        page = context.pages[0] if context.pages else context.new_page()
        events = BrowserEvents(context)
        page.set_content('<html lang="ko"><meta charset="utf-8"><title>WhoGa NAS 브라우저</title>'
                         '<body style="font:24px sans-serif;padding:60px;background:#edf3ed;color:#244b36">'
                         '<h1>WhoGa 브라우저 준비 완료</h1><p>관리 화면에서 원문 열기 또는 수집을 시작하세요.</p>'
                         '<p>이 창이 실제 수집에 사용됩니다.</p></body></html>')
        page.bring_to_front()
        while context.pages:
            context.pages[0].wait_for_timeout(1000)
            events.persist('/output/browser-diagnostics.json')


if __name__ == '__main__':
    main()
