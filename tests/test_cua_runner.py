"""Exercise the wheel collector's completeness and data preservation contracts."""
import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import cua_action_runner as runner
from monitor import ROOT, ValidationError, atomic_json, read_json, save_snapshot


RAW = (ROOT / 'tests/fixtures/naver_copied.txt').read_text()
CONFIG = read_json(ROOT / 'config.json')


def frame(count=2, total=2, bottom=True, raw=RAW):
    return {'sourceReady': True, 'declaredCount': total, 'cardCount': count,
            'atBottom': bottom, 'text': raw,
            'rect': {'x': 0, 'y': 0, 'width': 400, 'height': 800}}


class Page:
    viewport_size = {'width': 1280, 'height': 900}

    def __init__(self, frames):
        self.frames, self.reads, self.wheels = frames, 0, []
        self.mouse = types.SimpleNamespace(move=lambda *args: None,
                                          wheel=lambda x, y: self.wheels.append((x, y)))

    def wait_for_timeout(self, ms):
        pass

    def evaluate(self, script):
        result = self.frames[min(self.reads, len(self.frames) - 1)]
        self.reads += 1
        return result


class CollectorTests(unittest.TestCase):
    def collect(self, page, max_reads=100):
        self.ax_reads = []
        self.report = {}
        cdp = types.SimpleNamespace(send=lambda *args: self.ax_reads.append(args))
        return runner.collect_panel(page, cdp, CONFIG, self.report, max_reads=max_reads)

    def test_complete_counts_still_require_bottom_and_two_reads(self):
        page = Page([frame(bottom=False), frame(), frame()])
        snapshot = self.collect(page)
        self.assertEqual(len(snapshot['items']), 2)
        self.assertEqual(self.report['stableReads'], 2)
        self.assertEqual(page.reads, 3)
        self.assertEqual(len(page.wheels), 12)
        self.assertEqual(len(self.ax_reads), 3)

    def test_long_plateau_before_bottom_continues(self):
        partial = frame(1, 2, False, RAW.split('수성범어W 101동')[0])
        page = Page([partial] * 12 + [frame(), frame()])
        self.collect(page)
        self.assertEqual(len(page.wheels), 12 * 12)

    def test_partial_and_parser_mismatch_are_rejected(self):
        for state in [frame(count=1), frame(raw=RAW.split('수성범어W 101동')[0])]:
            with self.subTest(state=state), self.assertRaisesRegex(ValidationError, '전체 목록 검증 실패'):
                self.collect(Page([state]))

    def test_changed_total_and_restricted_screen_stop(self):
        with self.assertRaisesRegex(ValidationError, '총수가 변경'):
            self.collect(Page([frame(bottom=False), frame(total=3)]))
        page = Page([frame(raw='접근이 제한되었습니다')])
        with self.assertRaisesRegex(ValidationError, '접근 제한'):
            self.collect(page)
        self.assertEqual(page.wheels, [])

    def test_same_count_changed_content_resets_stability(self):
        page = Page([frame(), frame(raw=RAW.replace('5억 8,000', '5억 9,000'))])
        self.collect(page)
        self.assertEqual(page.reads, 3)

    def test_lost_panel_fails_without_key_error(self):
        with self.assertRaises(ValidationError):
            self.collect(Page([frame(bottom=False), {'sourceReady': False, 'text': ''}]))

    def test_target_url_does_not_mix_other_complexes_or_filters(self):
        self.assertEqual(runner.validate_target(CONFIG['sourceUrl'], CONFIG), CONFIG['sourceUrl'])
        for url in [CONFIG['sourceUrl'].replace('140635', '123'),
                    CONFIG['sourceUrl'].replace('A1', 'B1'),
                    CONFIG['sourceUrl'] + '&articleTradeTypes=B1']:
            with self.assertRaises(ValidationError):
                runner.validate_target(url, CONFIG)


class PersistenceTests(unittest.TestCase):
    def prepare(self, directory):
        original = read_json(ROOT / 'data/2026-10-18.json')
        save_snapshot(directory, copy.deepcopy(original))
        manual = copy.deepcopy(original)
        manual['label'] = 'same-day alternate'
        atomic_json(directory / '2026-10-18_manual_test.json', manual)
        return original

    def test_success_generates_compatible_json_and_keeps_history(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            original = self.prepare(directory)
            old_bytes = (directory / '2026-10-18.json').read_bytes()
            snapshot = copy.deepcopy(original)
            snapshot['date'] = '2026-10-22'
            runner.persist_snapshot(directory, snapshot)
            index = read_json(directory / 'index.json')
            self.assertEqual(index['latest'], '2026-10-22')
            self.assertEqual(len(index['snapshots']), 3)
            self.assertTrue(all('file' in entry and 'id' in entry for entry in index['snapshots']))
            self.assertEqual((directory / '2026-10-18.json').read_bytes(), old_bytes)
            self.assertEqual(read_json(directory / 'status.json')['lastAttemptResult'], 'success')

    def test_browser_exception_records_only_failure_status(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / 'data'
            self.prepare(directory)
            before = {path.name: path.read_bytes() for path in directory.glob('*.json')}
            with patch.object(runner, 'collect_browser', side_effect=TimeoutError('initial response timeout')):
                code = runner.main(['--data-dir', str(directory), '--evidence-dir', str(Path(temp) / 'evidence')])
            self.assertEqual(code, 1)
            for name, content in before.items():
                if name != 'status.json':
                    self.assertEqual((directory / name).read_bytes(), content)
            status = read_json(directory / 'status.json')
            self.assertEqual(status['lastAttemptResult'], 'failed')
            self.assertIn('lastSuccessAt', status)
            self.assertFalse(read_json(Path(temp) / 'evidence/report.json')['ok'])

    def test_failed_file_replacement_rolls_back_prepared_json(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            snapshot = self.prepare(directory)
            before = {path.name: path.read_bytes() for path in directory.glob('*.json')}
            snapshot['date'] = '2026-10-22'
            original_replace = runner.os.replace

            def fail_index(source, destination):
                if Path(destination) == directory / 'index.json':
                    raise OSError('simulated write failure')
                return original_replace(source, destination)

            with patch.object(runner.os, 'replace', side_effect=fail_index), self.assertRaises(OSError):
                runner.persist_snapshot(directory, snapshot)
            self.assertEqual({p.name: p.read_bytes() for p in directory.glob('*.json')}, before)


class DeploymentTests(unittest.TestCase):
    def test_site_verification_rejects_stale_data(self):
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            (site / 'data').mkdir()
            (site / 'index.html').write_bytes(b'<html>new build</html>')
            atomic_json(site / 'data/index.json', {'snapshots': [{'file': '2026-10-22.json'}]})
            atomic_json(site / 'data/status.json', {'lastAttemptResult': 'success'})
            atomic_json(site / 'data/2026-10-22.json', {'items': ['new']})

            class Response:
                status = 200

                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    pass

                def read(self):
                    return self.payload

            def response(url, timeout):
                path = url.split('https://example.test/')[1].split('?')[0]
                result = Response()
                result.payload = (site / path).read_bytes()
                if stale[0] and path == 'data/status.json':
                    result.payload = b'old status'
                return result

            stale = [False]
            with patch.object(runner, 'urlopen', side_effect=response):
                runner.verify_site('https://example.test/', site, attempts=1)
                stale[0] = True
                with self.assertRaisesRegex(ValidationError, '일치하지 않습니다'):
                    runner.verify_site('https://example.test/', site, attempts=1)


if __name__ == '__main__':
    unittest.main()
