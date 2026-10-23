import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
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

if __name__ == '__main__':
    unittest.main()
