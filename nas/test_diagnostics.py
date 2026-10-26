import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import diagnostics
import version

spec = importlib.util.spec_from_file_location('diagnostic_run', Path(__file__).with_name('run.py'))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class DiagnosticsTests(unittest.TestCase):
    def test_count_heading_supports_optional_suffix_without_using_sale_summary(self):
        for text, expected in [('매물 121', 121), ('매물 1,234개', 1234), ('매물 12 건', 12),
                               ('매물122개도움말 보기', 122), ('매물\n122\n개\n도움말 보기', 122), ('매물 0', 0)]:
            self.assertEqual(run.collector.parse_header_count(text), expected)
        for text in ('매매 121', '등록매물 121', '매물 로딩중'):
            with self.assertRaises(ValueError):
                run.collector.parse_header_count(text)

    def test_selects_complex_tab_instead_of_chrome_settings(self):
        settings = SimpleNamespace(url='chrome://settings/content/javascript')
        complex_page = SimpleNamespace(url=run.URL + '?tab=article')
        context = SimpleNamespace(pages=[settings, complex_page])
        self.assertIs(run.choose_page(context, run.URL), complex_page)

    def test_urls_and_errors_redact_credentials_and_unknown_query_values(self):
        url = 'https://user:secret@example.com/path?tab=article&token=secret#private'
        value = diagnostics.clean({'url': diagnostics.safe_url(url), 'error': 'Bearer secret github_pat_abc123 ' + url})
        serialized = json.dumps(value)
        self.assertNotIn('secret', serialized)
        self.assertNotIn('user:', serialized)
        self.assertNotIn('private', serialized)
        self.assertIn('tab=article', value['url'])
        self.assertNotIn('github_pat_abc123', serialized)

    def test_response_records_csp_without_recording_cookie_or_auth_headers(self):
        context = SimpleNamespace(pages=[], on=lambda *args: None)
        events = diagnostics.BrowserEvents(context)
        response = SimpleNamespace(url=run.URL, status=200, request=SimpleNamespace(resource_type='document'), headers={
            'content-security-policy': "script-src 'none'", 'set-cookie': 'private-cookie', 'authorization': 'private-auth'})
        events.response(response)
        serialized = json.dumps(events.snapshot())
        self.assertIn("script-src 'none'", serialized)
        self.assertNotIn('private-cookie', serialized)
        self.assertNotIn('private-auth', serialized)

    def test_classification_separates_block_error_loading_and_visible_cards(self):
        for snapshot, expected in [
            ({'bodyText': '비정상적인 접근입니다'}, 'access-or-verification-screen'),
            ({'title': '500 Internal Server Error'}, 'error-screen'),
            ({'cardCount': 2}, 'listing-cards-visible'),
            ({'panelPresent': True, 'cardCount': 0}, 'loading-or-empty-list'),
            ({'environment': {'mobile': True}}, 'mobile-layout-without-desktop-panel'),
        ]:
            result = diagnostics.classify(snapshot, [])
            self.assertEqual(result['pageState'], expected)
            self.assertFalse(result['cspBlockedDuringRun'])
        self.assertTrue(diagnostics.classify({}, [{'kind': 'browser-blocked', 'blockedReason': 'csp'}])['cspBlockedDuringRun'])
        self.assertFalse(diagnostics.classify({}, [{'kind': 'csp-violation', 'reportOnly': True}])['cspBlockedDuringRun'])
        self.assertTrue(diagnostics.classify({}, [{'kind': 'request-failed', 'failure': 'net::ERR_INSUFFICIENT_RESOURCES'}])['resourceFailureDuringRun'])
        self.assertFalse(diagnostics.classify({}, [{'kind': 'http-response', 'status': 500}])['resourceFailureDuringRun'])
        self.assertTrue(diagnostics.classify({}, [], {'insufficientResourcesErrors': 1})['resourceFailureDuringRun'])

    def test_fingerprint_changes_with_source_but_not_packaging_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in version.RUNTIME_FILES + ['nas/static/app.js']:
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('fixture')
            first = version.source_fingerprint(root)
            (root / 'nas/source-version.json').write_text(json.dumps({'sourceCommit': 'a' * 40}))
            self.assertEqual(version.source_fingerprint(root), first)
            (root / 'experiments/supplied-v2/collector.py').write_text('changed')
            self.assertNotEqual(version.source_fingerprint(root), first)

    def test_diagnostics_written_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'diagnostics.json'
            diagnostics.write_json(file, {'error': 'Bearer private'})
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)
            self.assertNotIn('private', file.read_text())


if __name__ == '__main__':
    unittest.main()
