"""Korean wall-clock scheduling, restart recovery and automatic upload gates."""
import base64
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('schedule_web', Path(__file__).with_name('web.py'))
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=web.SEOUL).timestamp()


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        with patch.object(web.time, 'time', return_value=at(22, 8)):
            self.app = self.load()

    def tearDown(self):
        self.tmp.cleanup()

    def load(self):
        return web.App(self.root / 'config', self.root / 'output')

    def enable(self, now=at(22, 8)):
        with patch.object(web.time, 'time', return_value=now):
            self.app.settings(dict(scheduleEnabled=True, scheduleMode='daily', dailyTime='08:45'))

    def test_wall_clock_uses_seoul_and_rolls_over_at_exact_slot(self):
        self.assertEqual(web.next_run(web.DEFAULT, at(22, 8, 44)), at(22, 8, 45))
        self.assertEqual(web.next_run(web.DEFAULT, at(22, 8, 45)), at(23, 8, 45))
        midnight = dict(web.DEFAULT, dailyTime='00:05')
        self.assertEqual(web.next_run(midnight, at(22, 0, 4)), at(22, 0, 5))
        self.assertEqual(web.next_run(midnight, at(22, 23, 59)), at(23, 0, 5))

    def test_invalid_modes_and_times_leave_settings_unchanged(self):
        for value in ('24:00', '8:45', '08:60', None, 845):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.app.settings({'dailyTime': value})
        with self.assertRaises(ValueError):
            self.app.settings({'scheduleMode': 'cron'})
        self.assertEqual(self.app.config['dailyTime'], '08:45')

    def test_existing_interval_settings_are_preserved(self):
        legacy = {k: v for k, v in web.DEFAULT.items() if k not in ('scheduleMode', 'dailyTime')}
        legacy.update(intervalMinutes=67, scheduleEnabled=True)
        web.atomic(self.root / 'config/settings.json', legacy)
        with patch.object(web.time, 'time', return_value=at(22, 8)):
            migrated = self.load()
        self.assertEqual(migrated.config['scheduleMode'], 'interval')
        self.assertEqual(migrated.state['nextRun'], at(22, 8) + 67 * 60)

    def test_manual_browser_checks_do_not_shift_daily_slot(self):
        self.enable()
        with patch.object(web.time, 'time', return_value=at(22, 8, 30)), patch.object(web.threading, 'Thread'):
            self.app.start('smoke')
        self.assertEqual(self.app.state['nextRun'], at(22, 8, 45))
        self.assertNotIn('lastDailyDate', self.app.state)

    def test_daily_runs_once_and_restart_retains_tomorrow(self):
        self.enable()
        with patch.object(web.time, 'time', return_value=at(22, 8, 44)):
            self.assertFalse(self.app.run_due())
        with patch.object(web.time, 'time', return_value=at(22, 8, 45)), patch.object(web.threading, 'Thread'):
            self.assertTrue(self.app.run_due())
        self.assertEqual(self.app.state['lastDailyDate'], '2026-10-22')
        self.assertEqual(self.app.state['nextRun'], at(23, 8, 45))
        with patch.object(web.time, 'time', return_value=at(22, 9)):
            restarted = self.load()
            self.assertFalse(restarted.run_due())
        self.assertEqual(restarted.state['result'], 'interrupted')
        self.assertEqual(restarted.state['nextRun'], at(23, 8, 45))

    def test_recovery_runs_once_without_backfilling_old_days(self):
        self.enable(now=at(20, 8))
        with patch.object(web.time, 'time', return_value=at(22, 7)), patch.object(web.threading, 'Thread'):
            restarted = self.load()
            self.assertTrue(restarted.run_due())
            restarted.state['running'] = False
            self.assertFalse(restarted.run_due())
        self.assertEqual(restarted.state['nextRun'], at(23, 8, 45))

    def test_upload_in_progress_defers_due_job(self):
        self.enable()
        self.app.state['upload'] = {'status': 'running'}
        with patch.object(web.time, 'time', return_value=at(22, 9)):
            self.assertFalse(self.app.run_due())
        self.assertEqual(self.app.state['nextRun'], at(22, 8, 45))

    def test_settings_save_does_not_move_pending_schedule(self):
        self.enable()
        with patch.object(web.time, 'time', return_value=at(22, 9)):
            self.app.settings({'githubToken': 'test-token'})
        self.assertEqual(self.app.state['nextRun'], at(22, 8, 45))
        with patch.object(web.time, 'time', return_value=at(22, 9)):
            self.app.settings({'dailyTime': '10:15'})
        self.assertEqual(self.app.state['nextRun'], at(22, 10, 15))

    def test_scheduled_date_guard_prevents_duplicate_after_time_change(self):
        self.enable()
        self.app.state['lastDailyDate'] = '2026-10-22'
        with patch.object(web.time, 'time', return_value=at(22, 8, 45)):
            self.assertFalse(self.app.run_due())
            self.app.settings({'dailyTime': '10:15'})
        self.assertEqual(self.app.state['nextRun'], at(23, 10, 15))

    def prepare_result(self):
        job, run_id = 'a' * 32, 'b' * 32
        self.app.settings(dict(githubToken='test-token', autoUpload=True))
        folder = self.app.output / 'jobs' / job
        payload = dict(mode='full', runId=run_id, target={'sourceUrl': self.app.config['url']},
                       displayedCardCount=1, collectedCardCount=1, articleCount=1,
                       cards=[{'name': '한글'}], articles=[{'id': 'fixture'}])
        web.atomic(folder / 'runs' / run_id / 'full.json', payload)
        web.atomic(folder / 'status.json', dict(status='full-passed', url=self.app.config['url'], runId=run_id))
        self.app.state.update(running=True, result='running')
        return job, payload

    def test_full_success_automatically_uploads_exact_validated_json(self):
        job, payload = self.prepare_result()

        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with patch.object(web.subprocess, 'Popen') as process, patch.object(web.threading, 'Thread', ImmediateThread), \
                patch.object(web, 'github', return_value={'content': {'html_url': 'https://github.com/fixture'}}) as request:
            process.return_value.wait.return_value = 0
            self.app.worker('full', job, self.app.config.copy())
        args = request.call_args.args
        self.assertEqual(args[1], '/contents/nas-imports/140635/' + payload['runId'] + '.json')
        self.assertEqual(args[3]['branch'], 'map-collector-v2')
        self.assertEqual(json.loads(base64.b64decode(args[3]['content'])), payload)
        self.assertEqual(self.app.state['upload']['status'], 'success')

    def test_failed_collection_never_uploads_even_if_success_file_exists(self):
        job, _ = self.prepare_result()
        with patch.object(web.subprocess, 'Popen') as process, patch.object(web, 'github') as request:
            process.return_value.wait.return_value = 1
            self.app.worker('full', job, self.app.config.copy())
        request.assert_not_called()
        self.assertEqual(self.app.state['result'], 'failed')


if __name__ == '__main__':
    unittest.main()
