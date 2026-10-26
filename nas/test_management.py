import tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch
import web,telegram_setup as tg
class ManagementTests(unittest.TestCase):
 def test_target_run_isolated_and_unknown_rejected(self):
  with tempfile.TemporaryDirectory() as d,patch.object(web.threading,'Thread') as thread:
   app=web.App(Path(d)/'config',Path(d)/'output');app.config['targets']=[dict(complexNo='123',label='추가')]
   with self.assertRaises(ValueError):app.start('full',target='999')
   app.start('full',target='123');self.assertEqual(thread.call_args.kwargs['args'][2]['url'],'https://fin.land.naver.com/complexes/123')
 def test_json_listing_uses_successful_target_only(self):
  with tempfile.TemporaryDirectory() as d:
   app=web.App(Path(d)/'c',Path(d)/'o');job='a'*32;run='b'*32;folder=app.output/'jobs'/job
   web.atomic(folder/'status.json',dict(url='https://fin.land.naver.com/complexes/123',runId=run,status='full-passed',full=dict(cards=2,articles=3)))
   web.atomic(folder/'runs'/run/'full.json',dict(mode='full'))
   self.assertEqual(app.collections()['123']['json'],f'/artifacts/{job}/{run}/full.json')
 def test_pair_requires_private_matching_challenge(self):
  session=dict(username='test_bot',token='test',challenge='hg_test',expires=time.time()+100,nextCheck=0,offset=0)
  event=dict(update_id=1,message=dict(text='/start wrong',chat=dict(id=123,type='private'),**{'from':dict(id=123)}))
  with patch.object(tg,'call',return_value=[event]),self.assertRaises(ValueError):tg.pair(session)
  session['nextCheck']=0;event['message']['text']='/start hg_test'
  with patch.object(tg,'call',return_value=[event]):self.assertEqual(tg.pair(session)['chatId'],123)
 def test_webhook_not_removed_and_token_hidden(self):
  with patch.object(tg,'call',side_effect=[dict(is_bot=True,username='test_bot'),dict(url='https://existing')]) as call,self.assertRaises(ValueError):tg.begin('token')
  self.assertEqual([x.args[1] for x in call.call_args_list],['getMe','getWebhookInfo'])
  with tempfile.TemporaryDirectory() as d:
   app=web.App(Path(d)/'c',Path(d)/'o');web.atomic(app.config_dir/'telegram.json',dict(token='private-secret',chatId=123,username='test_bot',enabled=False))
   self.assertNotIn('private-secret',str(app.snapshot()))
