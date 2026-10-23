"""Real local HTTP check for the existing Korean snapshot filename regression."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from monitor import atomic_json
import verify_pages


class VerificationTests(unittest.TestCase):
    def test_encoded_legacy_history_paths_are_requested_and_compared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            expected={'date':'2026-10-19','run_id':'trial-1'}
            for path in ('data/2026-10-19.json','whoga-naver-collector/latest.json',
                         'whoga-naver-collector/snapshot-2026-10-19.json'):
                atomic_json(root/path,expected)
            atomic_json(root/'data/index.json',{'snapshots':[{'file':'2026-10-17_118건.json'}]})
            atomic_json(root/'data/2026-10-17_118건.json',{'count':118})
            atomic_json(root/'whoga-naver-collector/history/과거.json',{'preserved':True})
            atomic_json(root/'whoga-naver-collector/evidence/validation.json',{'status':'pass'})
            (root/'index.html').write_text('app')
            (root/'assets').mkdir();(root/'assets/app.mjs').write_text('app')
            requested=[]
            class Handler(SimpleHTTPRequestHandler):
                def log_message(self,*args):pass
                def do_GET(self):
                    requested.append(self.path)
                    super().do_GET()
            server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(root)))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with patch.object(verify_pages,'ROOT',root):
                    verify_pages.verify(f'http://127.0.0.1:{server.server_port}',expected,attempts=1)
            finally:server.shutdown();thread.join();server.server_close()
            self.assertTrue(any('118%EA%B1%B4.json' in p for p in requested))
            self.assertTrue(any('/history/%EA%B3%BC%EA%B1%B0.json' in p for p in requested))


if __name__=='__main__':unittest.main()
