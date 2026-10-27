"""Real browser against local dashboard. All Telegram calls are mocked."""
import argparse,tempfile,threading
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
import web
parser=argparse.ArgumentParser();parser.add_argument('--chromium');args=parser.parse_args()
with tempfile.TemporaryDirectory() as folder:
 started=[False]
 app=web.App(Path(folder)/'config',Path(folder)/'output')
 def call(token,method,data=None):
  if method=='getMe':return dict(is_bot=True,username='whoga_test_bot')
  if method=='getWebhookInfo':return dict(url='')
  if method=='getUpdates' and not started[0]:return []
  if method=='getUpdates':return [dict(update_id=1,message=dict(text='/start '+app.telegram_session['challenge'],chat=dict(type='private',id=123),**{'from':dict(id=123)}))]
  return dict(message_id=1)
 server=web.ThreadingHTTPServer(('127.0.0.1',0),web.handler(app,'test-only-password'));threading.Thread(target=server.serve_forever,daemon=True).start()
 with patch.object(web.telegram_setup,'call',side_effect=call),sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
  page=browser.new_page(http_credentials={'username':'admin','password':'test-only-password'});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
  page.route('**/api/status',lambda route:route.fulfill(status=503,json=dict(error='Test: unrelated collection status unavailable')))
  page.goto('http://127.0.0.1:'+str(server.server_port));expect(page.locator('#tgState')).to_contain_text('연결되지 않음')
  page.locator('#tgToken').fill('123456:'+('x'*35));page.locator('#tgBegin').click();page.wait_for_selector('#tgOpen:visible')
  assert page.locator('#tgToken').input_value()==''
  assert page.locator('#tgCommand').input_value()=='/start '+app.telegram_session['challenge']
  assert not page.locator('#tgPair').is_visible()
  link=page.locator('#tgOpen').get_attribute('href');page.reload();page.wait_for_selector('#tgOpen:visible');assert page.locator('#tgOpen').get_attribute('href')==link
  # Simulate the user's one Telegram Start action. No NAS confirmation click.
  started[0]=True
  expect(page.locator('#tgState')).to_contain_text('연결됨:',timeout=15000)
  page.locator('#tgTest').click();expect(page.locator('#tgMessage')).to_contain_text('테스트 메시지를 보냈습니다')
  page.locator('#tgEnable').click();expect(page.locator('#tgState')).to_contain_text('켜짐')
  page.locator('#tgDisable').click();expect(page.locator('#tgState')).to_contain_text('꺼짐')
  page.locator('#tgOff').click();expect(page.locator('#tgState')).to_contain_text('연결되지 않음')
  assert not errors,errors;browser.close()
 server.shutdown()
print('PASS: automatic pairing without NAS confirmation, hidden fallback, reload recovery, notification controls')
