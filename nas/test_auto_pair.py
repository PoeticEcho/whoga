import tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import web
class AutoPairTests(unittest.TestCase):
 def test_waiting_keeps_existing_connection_and_matching_message_completes(self):
  with tempfile.TemporaryDirectory() as folder:
   app=web.App(Path(folder)/'c',Path(folder)/'o')
   old=dict(token='old-token',chatId=42,username='old_bot',enabled=True)
   web.atomic(app.config_dir/'telegram.json',old)
   app.telegram_session=dict(token='new-token',username='new_bot',challenge='hg_test',expires=time.time()+600,offset=0,nextCheck=0)
   with patch.object(web.telegram_setup,'call',return_value=[]):self.assertTrue(app.telegram_action(dict(action='auto-pair'))['pending'])
   self.assertEqual(web.read(app.config_dir/'telegram.json',{}),old)
   app.telegram_session['nextCheck']=0
   event=dict(update_id=1,message=dict(text='/start hg_test',chat=dict(id=123,type='private'),**{'from':dict(id=123)}))
   with patch.object(web.telegram_setup,'call',return_value=[event]):self.assertNotIn('pending',app.telegram_action(dict(action='auto-pair')))
   self.assertEqual(web.read(app.config_dir/'telegram.json',{})['chatId'],123)
   self.assertIsNone(app.telegram_session)
