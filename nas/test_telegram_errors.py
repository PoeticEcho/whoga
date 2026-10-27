import unittest,socket,ssl
from unittest.mock import patch
from urllib.error import HTTPError,URLError
import telegram_setup as tg
class TelegramErrorTests(unittest.TestCase):
 def test_errors_are_actionable_without_token_leak(self):
  token='123456:'+('x'*35)
  for error,expected in [(HTTPError('secret',401,'Unauthorized',{},None),'토큰'),(HTTPError('secret',409,'Conflict',{},None),'다른 프로그램'),(URLError(ssl.SSLError('secret')),'인증서'),(URLError('secret'),'DNS'),(socket.timeout('secret'),'초과')]:
   with self.subTest(expected=expected),patch.object(tg,'urlopen',side_effect=error),self.assertRaises(ValueError) as raised:tg.call(token,'getMe')
   self.assertIn(expected,str(raised.exception));self.assertNotIn(token,str(raised.exception));self.assertNotIn('secret',str(raised.exception))
