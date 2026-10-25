"""Headed Chromium launch and measured emulation shared by collection and comparison."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.request import urlopen

@contextmanager
def launch(pw, launcher, directory, executable=None, port=9223):
    executable = executable or pw.chromium.executable_path
    context = browser = process = None
    try:
        if launcher == 'playwright':
            context = pw.chromium.launch_persistent_context(
                str(directory), executable_path=executable, headless=False, chromium_sandbox=False,
                ignore_default_args=['--disable-dev-shm-usage'], viewport=None,
                args=['--lang=ko-KR', '--window-size=1440,1000'])
            browser = context.browser
        else:
            # Same Chromium binary, started as an ordinary process. CDP observes/operates it.
            # No webdriver JS patch, stealth injection, CSP bypass or ignored TLS errors.
            default = directory / 'Default'
            default.mkdir(parents=True)
            preferences = default / 'Preferences'
            try:
                settings = json.loads(preferences.read_text())
            except (OSError, ValueError):
                settings = {}
            settings.setdefault('intl', {})['accept_languages'] = 'ko-KR,ko,en-US,en'
            preferences.write_text(json.dumps(settings))
            process = subprocess.Popen([
                executable, '--no-sandbox', '--no-first-run', '--no-default-browser-check',
                '--user-data-dir=' + str(directory), '--remote-debugging-address=127.0.0.1',
                '--remote-debugging-port=' + str(port), '--lang=ko-KR', '--window-size=1440,1000', 'about:blank'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env={k: v for k, v in os.environ.items() if k != 'DASHBOARD_PASSWORD'})
            deadline = time.monotonic() + 25
            while True:
                if process.poll() is not None:
                    raise RuntimeError('일반 Chromium 실행이 종료됐습니다.')
                try:
                    with urlopen(f'http://127.0.0.1:{port}/json/version', timeout=1):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('일반 Chromium 연결 시간 초과')
                    time.sleep(.2)
            browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
            context = browser.contexts[0]
        yield browser, context
    finally:
        try:
            if browser and process:
                session = browser.new_browser_cdp_session()
                try:
                    session.send('Browser.close')
                except Exception:
                    pass
            elif context:
                context.close()
        finally:
            if process:
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def configure(page, profile, width, height, browser_version):
    session = page.context.new_cdp_session(page)
    session.send('Emulation.setDeviceMetricsOverride', dict(width=width, height=height,
                 deviceScaleFactor=1, mobile=profile == 'android', screenWidth=width, screenHeight=height))
    session.send('Emulation.setTouchEmulationEnabled', {'enabled': profile == 'android'})
    session.send('Emulation.setTimezoneOverride', {'timezoneId': 'Asia/Seoul'})
    session.send('Emulation.setLocaleOverride', {'locale': 'ko-KR'})
    # Keep UA/Client Hints consistent; this remains emulation on Linux, not a real phone.
    native = page.evaluate('''async () => ({ua:navigator.userAgent,
        data:navigator.userAgentData?.toJSON(),
        entropy:await navigator.userAgentData?.getHighEntropyValues(['platformVersion','architecture','bitness','model'])})''')
    version = browser_version.split('.')[0]
    data = native.get('data') or {'brands': [{'brand': 'Chromium', 'version': version}], 'platform': 'Linux'}
    entropy = native.get('entropy') or {}
    # Supplying a UA without metadata suppresses Client Hints even on desktop.
    metadata = dict(brands=data['brands'], fullVersion=browser_version,
                    platform=data['platform'], platformVersion=entropy.get('platformVersion', ''),
                    architecture=entropy.get('architecture', 'x86'), bitness=entropy.get('bitness', '64'),
                    model=entropy.get('model', ''), mobile=False)
    override = dict(userAgent=native['ua'], acceptLanguage='ko-KR,ko,en-US,en',
                    userAgentMetadata=metadata)
    if profile == 'android':
        override.update(userAgent=f'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
                        f'(KHTML, like Gecko) Chrome/{version}.0.0.0 Mobile Safari/537.36', platform='Linux armv8l',
                        userAgentMetadata=dict(brands=data['brands'], fullVersion=browser_version,
                        platform='Android', platformVersion='13.0.0', architecture='', bitness='', model='Pixel 7', mobile=True))
    session.send('Network.setUserAgentOverride', override)
    return session



def bootstrap(page):
    # A trusted loopback origin exposes native Client Hints before navigation.
    # It also works before the dashboard has started, without external traffic.
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'<!doctype html><title>WhoGa browser startup</title>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        page.goto(f'http://127.0.0.1:{server.server_port}', wait_until='domcontentloaded', timeout=5000)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
