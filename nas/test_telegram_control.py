import copy,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import web,telegram_control as control

class ControlTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.app=web.App(Path(self.tmp.name)/'c',Path(self.tmp.name)/'o')
  self.tg=dict(token='test-only',chatId=123,username='test_bot',enabled=False)
  web.atomic(self.app.config_dir/'telegram.json',self.tg)
 def event(self,uid=1,text='/collect',**fields):
  msg=dict(date=int(time.time()),text=text,chat=dict(id=123,type='private'),**{'from':dict(id=123)})
  msg.update(fields);return dict(update_id=uid,message=msg)
 def poll(self,events):
  def call(token,method,data):return events if method=='getUpdates' else {}
  with patch.object(web.telegram_setup,'call',side_effect=call) as api:
   control.poll(self.app);return api
 def test_own_command_starts_full_once_and_deduplicates_restart(self):
  with patch.object(web.threading,'Thread') as thread:
   api=self.poll([self.event()]);self.assertEqual(self.app.state['trigger'],'telegram');self.assertTrue(self.app.state['running']);thread.assert_called_once()
   self.assertIn('수집을 시작',api.call_args_list[-1].args[2]['text'])
   self.app.state['running']=False
   self.poll([self.event()]);thread.assert_called_once()
   self.app=web.App(self.app.config_dir,self.app.output)
   self.poll([self.event()]);thread.assert_called_once()
 def test_foreign_group_old_and_bot_messages_do_not_run_or_reply(self):
  for fields in [dict(chat=dict(id=999,type='private')),{'from':dict(id=999)},dict(chat=dict(id=123,type='group')),dict(date=1),{'from':dict(id=123,is_bot=True)}]:
   with self.subTest(fields=fields),patch.object(self.app,'start') as start:
    self.app.telegram_control_boot=time.time()
    # Unique IDs ensure deduplication does not hide authorization regressions.
    event=self.event(uid=int(time.time_ns()),**fields);api=self.poll([event]);start.assert_not_called();self.assertEqual(api.call_count,1)
 def test_registered_target_busy_and_unknown(self):
  self.app.config['targets']=[dict(complexNo='140634')]
  with patch.object(web.threading,'Thread'):
   self.poll([self.event(text='/collect 140634')]);self.assertTrue(self.app.state['activeUrl'].endswith('/140634'))
   job=self.app.state['jobId'];self.poll([self.event(uid=2)]);self.assertEqual(job,self.app.state['jobId'])
   self.app.state['running']=False
   api=self.poll([self.event(uid=3,text='/collect 999')]);self.assertIn('저장된 단지',api.call_args_list[-1].args[2]['text'])
 def test_disabled_and_pairing_do_not_poll(self):
  for enabled,session in [(False,None),(True,{'pending':True,'expires':time.time()+600})]:
   web.atomic(self.app.config_dir/'telegram.json',{**self.tg,'controlEnabled':enabled});self.app.telegram_session=session
   with patch.object(web.telegram_setup,'call') as api:control.poll(self.app);api.assert_not_called()
 def test_status_and_addressed_bot(self):
  self.assertEqual(control.command('/collect@test_bot 140635','test_bot'),('collect','140635'))
  self.assertEqual(control.command('/collect@other_bot','test_bot'),(None,None))
  api=self.poll([self.event(text='/status')]);self.assertIn('호가정리 상태',api.call_args_list[-1].args[2]['text'])
 def test_control_completion_is_sent_once_and_preserves_binding(self):
  self.app.state['telegramJob']=dict(jobId='a',binding=control.binding(self.tg))
  with patch.object(web.telegram_setup,'call') as api:
   self.app.telegram_job_result('a','수집 완료');self.app.telegram_job_result('a','수집 완료');api.assert_called_once()
