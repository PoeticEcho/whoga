import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import resources


class ResourceTests(unittest.TestCase):
    def test_cgroup_v2_reports_limit_usage_events_and_host_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group = root / 'sys/fs/cgroup'
            group.mkdir(parents=True)
            for name, value in {'memory.current': '123456', 'memory.max': '3221225472',
                                'memory.events': 'high 2\noom 1\noom_kill 1\n'}.items():
                (group / name).write_text(value)
            (root / 'proc').mkdir()
            (root / 'proc/meminfo').write_text('MemTotal: 6291456 kB\nMemAvailable: 2097152 kB\n')
            value = resources.memory_snapshot(root)
            self.assertEqual(value['version'], 2)
            self.assertEqual(value['currentBytes'], 123456)
            self.assertEqual(value['limitBytes'], 3 * 1024**3)
            self.assertEqual(value['events']['oom_kill'], 1)
            self.assertEqual(value['host']['MemAvailableBytes'], 2 * 1024**3)
            (group / 'memory.max').write_text('max')
            self.assertIsNone(resources.memory_snapshot(root)['limitBytes'])

    def test_synology_style_cgroup_v1_and_unlimited_value(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group = root / 'sys/fs/cgroup/memory'
            group.mkdir(parents=True)
            (group / 'memory.usage_in_bytes').write_text('456789')
            (group / 'memory.limit_in_bytes').write_text(str(3 * 1024**3))
            (group / 'memory.failcnt').write_text('5')
            value = resources.memory_snapshot(root)
            self.assertEqual(value['version'], 1)
            self.assertEqual(value['currentBytes'], 456789)
            self.assertEqual(value['limitBytes'], 3 * 1024**3)
            self.assertEqual(value['failCount'], 5)
            (group / 'memory.limit_in_bytes').write_text(str(2**63 - 4096))
            self.assertIsNone(resources.memory_snapshot(root)['limitBytes'])

    def test_filesystem_measurement_and_missing_mount_do_not_fail_run(self):
        with tempfile.TemporaryDirectory() as directory:
            value = resources.filesystem_snapshot(directory)
            self.assertGreater(value['totalBytes'], 0)
            self.assertGreater(value['availableBytes'], 0)
            self.assertIn('unavailable', resources.filesystem_snapshot(Path(directory) / 'missing'))

    def test_browser_switches_are_measured_without_retaining_full_arguments(self):
        class Session:
            def send(self, command):
                return {'processInfo': [{'id': os.getpid(), 'type': 'browser'}, {'id': 123, 'type': 'renderer'}]}

            def detach(self):
                pass

        browser = SimpleNamespace(contexts=[SimpleNamespace(pages=[object()])], new_browser_cdp_session=lambda: Session())
        with patch.object(Path, 'read_bytes', return_value=b'chromium\0--disable-dev-shm-usage\0--headless=new\0--secret=private-value\0'):
            value = resources.browser_snapshot(browser)
        self.assertTrue(value['sharedMemoryDisabled'])
        self.assertTrue(value['headless'])
        self.assertEqual(value['pageCount'], 1)
        self.assertEqual(value['processCounts']['renderer'], 1)
        self.assertNotIn('private-value', json.dumps(value))
        self.assertNotIn('secret', json.dumps(value))


if __name__ == '__main__':
    unittest.main()
