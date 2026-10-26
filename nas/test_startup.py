"""One first-start attempt, persistent claims, readiness and schedule coalescing."""
import copy
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import web
import browser_control

class StartupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.now=datetime(2026,10,26,8,tzinfo=web.SEOUL).timestamp()
        self.clock=patch.object(web.time,'time',return_value=self.now);self.clock.start()
        self.env=patch.dict(web.os.environ,{'WHOGA_STARTUP_COLLECT':'1'});self.env.start()
        self.ready=self.root/'ready';self.ready.touch()
        self.ready_patch=patch.object(browser_control,'READY',self.ready);self.ready_patch.start()
        self.connected=patch.object(browser_control,'desktop_connected',return_value=True);self.connected.start()
        self.threads=patch.object(web.threading,'Thread');self.threads.start()
        self.app=self.load()
    def load(self):return web.App(self.root/'config',self.root/'output')
    def tearDown(self):
        self.threads.stop();self.connected.stop();self.ready_patch.stop();self.env.stop();self.clock.stop();self.tmp.cleanup()
    def test_disabled_schedule_still_runs_full_once_after_ready(self):
        self.assertFalse(self.app.config['scheduleEnabled'])
        self.assertTrue(self.app.run_startup_once())
        self.assertEqual(self.app.state['mode'],'full')
        self.assertEqual(self.app.state['trigger'],'startup')
        self.assertFalse(self.app.run_startup_once())
        self.assertNotIn('lastDailyDate',self.app.state)
    def test_restart_after_interruption_or_failure_does_not_repeat(self):
        self.assertTrue(self.app.run_startup_once())
        restarted=self.load();self.assertEqual(restarted.state['result'],'interrupted')
        self.assertFalse(restarted.run_startup_once())
        restarted.state.update(result='failed',running=False);restarted.save()
        self.assertFalse(self.load().run_startup_once())
    def test_new_fingerprint_runs_but_return_to_old_build_does_not(self):
        self.app.run_startup_once();old=copy.deepcopy(self.app.build)
        self.app.state['running']=False;self.app.build={**old,'sourceFingerprint':'new'}
        self.assertTrue(self.app.run_startup_once())
        self.app.state['running']=False;self.app.build=old
        self.assertFalse(self.app.run_startup_once())
    def test_busy_and_unready_defer_without_claim(self):
        self.ready.unlink();self.assertFalse(self.app.run_startup_once());self.ready.touch()
        self.app.state['running']=True;self.assertFalse(self.app.run_startup_once())
        self.app.state['running']=False;self.app.state['upload']={'status':'running'}
        self.assertFalse(self.app.run_startup_once());self.app.state['upload']={'status':'not-configured'}
        self.assertFalse((self.root/'config/startup-collections.json').exists())
        self.assertTrue(self.app.run_startup_once())
    def test_due_daily_slot_is_consumed_by_startup(self):
        self.app.config.update(scheduleEnabled=True,dailyTime='08:00')
        self.app.state['nextRun']=self.now
        self.assertTrue(self.app.run_startup_once())
        self.assertEqual(self.app.state['lastDailyDate'],'2026-10-26')
        self.app.state['running']=False
        self.assertFalse(self.app.run_due())
        self.assertGreater(self.app.state['nextRun'],self.now)
    def test_future_daily_slot_and_settings_are_preserved(self):
        self.app.settings({'scheduleEnabled':True,'dailyTime':'09:00','autoUpload':True,'githubToken':'test-only'})
        config=copy.deepcopy(self.app.config);next_run=self.app.state['nextRun']
        self.app.run_startup_once()
        self.assertEqual(self.app.config,config);self.assertEqual(self.app.state['nextRun'],next_run)
        self.assertNotIn('lastDailyDate',self.app.state)
    def test_opt_out_never_claims(self):
        with patch.dict(web.os.environ,{'WHOGA_STARTUP_COLLECT':'0'}):self.assertFalse(self.app.run_startup_once())
        self.assertFalse((self.root/'config/startup-collections.json').exists())
    def test_marker_write_failure_prevents_worker(self):
        with patch.object(web,'atomic',side_effect=OSError('disk full')),patch.object(self.app,'start') as start:
            with self.assertRaises(OSError):self.app.run_startup_once()
            start.assert_not_called()

if __name__=='__main__':unittest.main()
