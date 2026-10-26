"""Offline browser checks for real dashboard markup, settings and upload gates."""
import argparse
import copy
import json
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
CHROMIUM = None
TARGET = 'https://fin.land.naver.com/complexes/140635'


class UploadGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True, **({'executable_path': CHROMIUM} if CHROMIUM else {}))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.data = dict(config=dict(url=TARGET, scheduleEnabled=True, scheduleMode='daily', dailyTime='08:00',
                                    intervalMinutes=1440, repository='PoeticEcho/whoga', branch='map-collector-v2',
                                    tokenStored=False, autoUpload=False),
                         state=dict(running=False, result='full-passed', mode='full', startedAt=1792969845,
                                    nextRun=1793055600, upload={'status':'not-configured'},
                                    lastResult=dict(status='full-passed', runId='a'*32, url=TARGET,
                                                    phase='full:normalize', full=dict(cards=122, articles=578))),
                         log='', build=dict(version='2.5.2',sourceCommit=None,sourceFingerprint='1'*64))
        self.requests=[]
        self.context=self.browser.new_context(viewport={'width':1440,'height':1000})
        self.page=self.context.new_page()
        self.errors=[]
        self.page.on('pageerror',lambda error:self.errors.append(str(error)))
        def route(route):
            request=route.request
            path=request.url.removeprefix('http://dashboard.test')
            if path=='/api/status':
                route.fulfill(json=self.data)
            elif path=='/api/settings':
                payload=request.post_data_json
                self.data['config'].update({k:v for k,v in payload.items() if k not in ('githubToken','clearToken')})
                if payload.get('githubToken'):self.data['config']['tokenStored']=True
                if payload.get('clearToken'):self.data['config']['tokenStored']=False
                self.requests.append(path)
                route.fulfill(json={'message':'saved'})
            elif path=='/api/upload':
                self.requests.append(path)
                config=self.data['config'];run=self.data['state']['lastResult']['runId']
                self.data['state']['upload']=dict(status='success',key=f"{config['repository']}:{config['branch']}:{run}",
                                                  url='https://github.com/PoeticEcho/whoga/blob/map-collector-v2/nas-imports/140635/'+run+'.json')
                route.fulfill(json={'message':'fixture upload'})
            elif path in ('/','/app.js','/style.css'):
                name='index.html' if path=='/' else path[1:]
                route.fulfill(body=(ROOT/'static'/name).read_text(),content_type={'index.html':'text/html','app.js':'text/javascript','style.css':'text/css'}[name])
            else:route.fulfill(status=404,body='')
        self.context.route('**/*',route)
        self.page.goto('http://dashboard.test/')
        self.page.wait_for_function("document.querySelector('#result').textContent === '전체 수집 성공'")

    def tearDown(self):
        self.assertEqual(self.errors,[])
        self.context.close()

    def refresh(self):
        self.page.evaluate('refresh()')

    def test_success_with_missing_token_explains_disabled_button(self):
        self.assertTrue(self.page.locator('#upload').is_disabled())
        self.assertEqual(self.page.locator('#uploadStatus').inner_text(),'토큰 등록 필요')
        self.assertIn('전체 수집은 성공',self.page.locator('#uploadHelp').inner_text())
        self.assertTrue(self.page.locator('#githubSettings').evaluate('el=>el.open'))
        self.assertIn('최종 결과: 전체 수집 성공',self.page.locator('#diagnosticSummary').inner_text())
        self.assertIn('마지막 단계: full:normalize',self.page.locator('#diagnosticSummary').inner_text())
        self.assertEqual(self.page.locator('#runTrigger').inner_text(),'실행 방식 미기록')
        self.assertEqual(self.requests,[])

    def test_save_token_clears_stale_not_configured_and_uploads_without_recollecting(self):
        self.page.locator('#githubToken').fill('local-fixture-token')
        self.assertIn('설정을 먼저 저장',self.page.locator('#uploadHelp').inner_text())
        self.page.locator('#settings button[type=submit]').click()
        self.page.wait_for_function("!document.querySelector('#upload').disabled")
        self.assertEqual(self.page.locator('#uploadStatus').inner_text(),'업로드 준비됨')
        self.assertIn('자동 업로드 꺼짐',self.page.locator('#autoUploadState').inner_text())
        self.assertEqual(self.page.locator('#githubToken').input_value(),'')
        self.page.locator('#upload').click()
        self.page.wait_for_function("document.querySelector('#uploadStatus').textContent==='업로드 완료'")
        self.assertTrue(self.page.locator('#upload').is_disabled())
        self.assertTrue(self.page.locator('#uploadLink').is_visible())
        self.assertEqual(self.requests,['/api/settings','/api/upload'])

    def test_old_success_does_not_mark_new_run_uploaded_and_failure_can_retry(self):
        self.data['config']['tokenStored']=True
        self.data['state']['upload']=dict(status='success',key='old-run',url='https://github.com/old')
        self.refresh()
        self.assertTrue(self.page.locator('#upload').is_enabled())
        self.assertFalse(self.page.locator('#uploadLink').is_visible())
        self.data['state']['upload']=dict(status='failed',key='PoeticEcho/whoga:map-collector-v2:'+'a'*32,message='fixture 403')
        self.refresh()
        self.assertEqual(self.page.locator('#uploadStatus').inner_text(),'업로드 실패')
        self.assertIn('fixture 403',self.page.locator('#uploadHelp').inner_text())
        self.assertTrue(self.page.locator('#upload').is_enabled())

    def test_busy_unsaved_probe_and_wrong_target_remain_blocked(self):
        self.data['config']['tokenStored']=True
        for patch_data, label in [({'running':True},'수집 중'),({'upload':{'status':'running'}},'업로드 중'),
                                  ({'result':'probe-passed'},'전체 수집 대기')]:
            saved=copy.deepcopy(self.data['state']);self.data['state'].update(patch_data);self.refresh()
            self.assertEqual(self.page.locator('#uploadStatus').inner_text(),label)
            self.assertTrue(self.page.locator('#upload').is_disabled())
            self.data['state']=saved
        self.data['config']['url']='https://fin.land.naver.com/complexes/999';self.refresh()
        self.assertTrue(self.page.locator('#upload').is_disabled())
        self.data['config']['url']=TARGET;self.refresh()
        self.page.locator('#branch').fill('another-branch')
        self.assertEqual(self.page.locator('#uploadStatus').inner_text(),'설정 저장 필요')
        self.assertTrue(self.page.locator('#upload').is_disabled())

    def test_config_link_and_trigger_explain_current_state(self):
        self.page.locator('#githubSettings summary').click()
        self.page.locator('#openGithubSettings').click()
        self.assertTrue(self.page.locator('#githubSettings').evaluate('el=>el.open'))
        self.data['config'].update(autoUpload=True,tokenStored=True)
        self.data['state']['trigger']='scheduled';self.refresh()
        self.assertIn('자동 업로드 켜짐',self.page.locator('#autoUploadState').inner_text())
        self.assertEqual(self.page.locator('#runTrigger').inner_text(),'예약 실행')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--chromium')
    options,rest=parser.parse_known_args();CHROMIUM=options.chromium
    unittest.main(argv=[__file__]+rest)
