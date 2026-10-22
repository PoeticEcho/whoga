import base64
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import socket
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('web', Path(__file__).with_name('web.py'))
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)

class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = web.App(self.root / 'config', self.root / 'output')

    def tearDown(self):
        self.tmp.cleanup()

    def test_token_never_returned_and_blank_preserves(self):
        self.app.settings({'githubToken': 'secret-test-token'})
        self.app.log_path.write_text('secret-test-token')
        self.assertNotIn('secret-test-token', json.dumps(self.app.snapshot()))
        self.app.settings({'githubToken': ''})
        self.assertEqual(self.app.config['githubToken'], 'secret-test-token')
        self.assertEqual((self.root / 'config/settings.json').stat().st_mode & 0o777, 0o600)

    def test_reject_arbitrary_url_and_invalid_interval(self):
        for patch_data in [{'url': 'http://127.0.0.1'}, {'url': 'https://fin.land.naver.com/complexes/140635?extra=1'}, {'intervalMinutes': 0}]:
            with self.assertRaises(ValueError):
                self.app.settings(patch_data)
        self.assertEqual(self.app.config['url'], web.DEFAULT['url'])

    def test_probe_and_stale_success_never_upload(self):
        self.app.state['result'] = 'probe-passed'
        with self.assertRaises(ValueError):
            self.app.start_upload()
        self.app.state.update(result='full-passed', lastResult={'url': 'https://fin.land.naver.com/complexes/1'})
        with self.assertRaises(ValueError):
            self.app.start_upload()

    def test_duplicate_run_blocked(self):
        self.app.state['running'] = True
        with self.assertRaises(ValueError):
            self.app.start('probe')
        with self.assertRaises(ValueError):
            self.app.settings({'intervalMinutes': 20})

    def test_restart_marks_interrupted(self):
        self.app.state.update(running=True, result='running', upload={'status': 'running'})
        self.app.save()
        restarted = web.App(self.root / 'config', self.root / 'output')
        self.assertFalse(restarted.state['running'])
        self.assertEqual(restarted.state['result'], 'interrupted')
        self.assertEqual(restarted.state['upload']['status'], 'failed')

    def test_upload_writes_only_nas_imports_and_encodes_data(self):
        payload = dict(runId='a'*32, cards=[{'name': '한글'}])
        config = dict(web.DEFAULT, githubToken='test-token')
        with patch.object(web, 'github', return_value={'content': {'html_url': 'https://github.com/example'}}) as mock:
            self.app.upload(payload, config, 'key')
        args = mock.call_args.args
        self.assertEqual(args[1], '/contents/nas-imports/140635/'+'a'*32+'.json')
        self.assertEqual(args[2], 'PUT')
        self.assertEqual(json.loads(base64.b64decode(args[3]['content'])), payload)
        self.assertNotIn('sha', args[3])
        self.assertEqual(self.app.state['upload']['status'], 'success')

    def test_gui_install_generates_unique_persistent_admin_password(self):
        with patch.dict(os.environ, {'DASHBOARD_PASSWORD': ''}):
            first = web.dashboard_password(self.root / 'gui-config')
            again = web.dashboard_password(self.root / 'gui-config')
        self.assertEqual(first, again)
        self.assertGreaterEqual(len(first), 12)
        secret_file = self.root / 'gui-config/admin-password.txt'
        self.assertEqual(secret_file.read_text().strip(), first)
        self.assertEqual(secret_file.stat().st_mode & 0o777, 0o600)

    def test_explicit_password_preserved_without_password_file(self):
        with patch.dict(os.environ, {'DASHBOARD_PASSWORD': 'owner-set-password-123'}):
            self.assertEqual(web.dashboard_password(self.root / 'provided'), 'owner-set-password-123')
        self.assertFalse((self.root / 'provided/admin-password.txt').exists())

    def test_invalid_explicit_password_fails_closed(self):
        with patch.dict(os.environ, {'DASHBOARD_PASSWORD': 'short'}):
            with self.assertRaises(SystemExit):
                web.dashboard_password(self.root / 'invalid')

    def test_http_auth_and_csrf(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), web.handler(self.app, 'test-password-123'))
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        auth = 'Basic ' + base64.b64encode(b'admin:test-password-123').decode()
        try:
            self.assertEqual(urlopen(base+'/health').status, 200)
            with self.assertRaises(HTTPError) as ctx:
                urlopen(base+'/api/status')
            self.assertEqual(ctx.exception.code, 401)
            with self.assertRaises(HTTPError) as ctx:
                urlopen(Request(base+'/api/settings', data=b'{}', headers={'Authorization': auth}))
            self.assertEqual(ctx.exception.code, 403)
            headers={'Authorization': auth, 'X-Whoga-Request': '1', 'Origin': 'https://evil.example'}
            with self.assertRaises(HTTPError) as ctx:
                urlopen(Request(base+'/api/settings', data=b'{}', headers=headers))
            self.assertEqual(ctx.exception.code, 403)
            headers['Origin'] = base
            self.assertEqual(urlopen(Request(base+'/api/settings', data=b'{}', headers=headers)).status, 200)
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_desktop_ticket_is_short_lived_and_single_use(self):
        ticket = self.app.desktop_ticket()
        self.assertTrue(self.app.use_desktop_ticket(ticket))
        self.assertFalse(self.app.use_desktop_ticket(ticket))
        ticket = self.app.desktop_ticket()
        with patch.object(web.time, 'monotonic', return_value=web.time.monotonic() + 31):
            self.assertFalse(self.app.use_desktop_ticket(ticket))

    def test_desktop_auth_origin_and_bidirectional_proxy(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), web.handler(self.app, 'test-password-123'))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        auth = 'Basic ' + base64.b64encode(b'admin:test-password-123').decode()
        upstream = socket.socket()
        upstream.bind(('127.0.0.1', 0));upstream.listen(1)
        observed = []

        def backend():
            with upstream.accept()[0] as connection:
                connection.settimeout(5)
                headers = b''
                while b'\r\n\r\n' not in headers:
                    headers += connection.recv(4096)
                observed.append(headers)
                connection.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n')
                data = connection.recv(32)
                connection.sendall(data)

        backend_thread = threading.Thread(target=backend, daemon=True)
        try:
            with self.assertRaises(HTTPError) as failure:
                urlopen(base + '/desktop/')
            self.assertEqual(failure.exception.code, 401)
            response = urlopen(Request(base + '/desktop/', headers={'Authorization': auth}))
            self.assertIn("img-src 'self' data: blob:", response.headers['Content-Security-Policy'])
            self.assertIn('client.js', response.read().decode())
            with self.assertRaises(HTTPError) as failure:
                urlopen(base + '/desktop/websockify?ticket=unknown')
            self.assertEqual(failure.exception.code, 403)
            request = Request(base + '/api/desktop-session', data=b'{}', headers={
                'Authorization': auth, 'X-Whoga-Request': '1', 'Origin': base})
            ticket = json.load(urlopen(request))['ticket']
            backend_thread.start()
            with patch.dict(os.environ, {'WHOGA_WEBSOCKIFY_PORT': str(upstream.getsockname()[1])}):
                with socket.create_connection(('127.0.0.1', server.server_port), timeout=5) as client:
                    client.sendall((f'GET /desktop/websockify?ticket={ticket} HTTP/1.1\r\n'
                                    f'Host: 127.0.0.1:{server.server_port}\r\nOrigin: {base}\r\n'
                                    f'Authorization: {auth}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                                    'Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: test-key\r\n\r\n').encode())
                    self.assertIn(b'101 Switching', client.recv(4096))
                    client.sendall(b'round-trip')
                    self.assertEqual(client.recv(32), b'round-trip')
            backend_thread.join(timeout=5)
            self.assertNotIn(b'Authorization', observed[0])
            self.assertFalse(self.app.use_desktop_ticket(ticket))
        finally:
            upstream.close();server.shutdown();server.server_close()

if __name__ == '__main__':
    unittest.main()
