import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import web
from plan import validate_plan

PLAN=dict(schemaVersion=1,enabled=True,intervalHours=6,targets=[dict(complexNo=n,label='단지 '+n) for n in ['140635','123','456']])
class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.app=web.App(Path(self.tmp.name)/'config',Path(self.tmp.name)/'output')
        self.app.config['githubToken']='test-only'
    def response(self,plan=PLAN):return dict(sha='a'*40,size=500,content=base64.b64encode(json.dumps(plan).encode()).decode())
    def test_plan_bounds_and_duplicates(self):
        self.assertEqual(validate_plan(PLAN)['intervalHours'],6)
        for patcher in [dict(intervalHours=True),dict(intervalHours=2),dict(targets=[]),dict(targets=PLAN['targets']+[PLAN['targets'][0]]),dict(targets=[dict(complexNo='../123')]),dict(targets=[dict(complexNo='123'),dict(complexNo='123')])]:
            with self.subTest(patcher=patcher),self.assertRaises(ValueError):validate_plan({**PLAN,**patcher})
    def test_apply_restart_and_rotation_consumes_failures(self):
        with patch.object(web,'github',side_effect=[self.response(),{'sha':'old'},{}]):self.assertTrue(self.app.sync_plan())
        self.assertTrue(self.app.config['autoUpload']);self.assertEqual(self.app.config['intervalMinutes'],360)
        with patch.object(web.threading,'Thread') as thread:
            for number in ['140635','123','456','140635']:
                self.app.state.update(running=False,nextRun=0,result='failed');self.assertTrue(self.app.run_due())
                self.assertEqual(thread.call_args.kwargs['args'][2]['url'].split('/')[-1],number)
                self.assertGreater(self.app.state['nextRun'],web.time.time()+350*60)
                self.assertFalse(self.app.run_due())
        self.app.state['running']=False;self.app.save()
        restarted=web.App(self.app.config_dir,self.app.output)
        self.assertEqual(restarted.state['targetCursor'],1);self.assertFalse(restarted.run_due())
    def test_missing_invalid_busy_preserve_settings(self):
        before=copy.deepcopy(self.app.config)
        error=ValueError('missing');error.status=404
        with patch.object(web,'github',side_effect=error):self.assertFalse(self.app.sync_plan())
        self.assertEqual(self.app.config,before)
        self.app.state['nextPlanCheck']=0
        with patch.object(web,'github',return_value=self.response({**PLAN,'intervalHours':0})):self.assertFalse(self.app.sync_plan())
        self.assertEqual(self.app.config,before)
        self.app.state.update(nextPlanCheck=0,running=True)
        with patch.object(web,'github') as github:self.assertFalse(self.app.sync_plan());github.assert_not_called()
    def test_ack_retry_does_not_reset_cursor_or_schedule(self):
        with patch.object(web,'github',side_effect=[self.response(),ValueError('network')]):self.assertFalse(self.app.sync_plan())
        self.app.state.update(nextPlanCheck=0,targetCursor=2);next_run=self.app.state['nextRun']
        with patch.object(web,'github',side_effect=[self.response(),{'sha':'old'},{}]):self.assertTrue(self.app.sync_plan())
        self.assertEqual(self.app.state['targetCursor'],2);self.assertEqual(self.app.state['nextRun'],next_run)
    def test_disabled_plan_does_not_start_after_build(self):
        with patch.object(web,'github',side_effect=[self.response({**PLAN,'enabled':False}),{'sha':'old'},{}]):self.assertTrue(self.app.sync_plan())
        self.assertFalse(self.app.run_due());self.assertFalse(self.app.run_startup_once())
