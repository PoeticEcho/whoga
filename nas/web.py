"""Authenticated LAN dashboard for a single NAS collector."""
import base64
import copy
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parent
DEFAULT = dict(url='https://fin.land.naver.com/complexes/140635', intervalMinutes=1440,
               scheduleEnabled=False, autoUpload=False, repository='PoeticEcho/whoga',
               branch='map-collector-v2', githubToken='')


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with tmp.open('x') as f:
        os.chmod(tmp, 0o600)
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def read(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return copy.deepcopy(default)


def validate(config):
    if not re.fullmatch(r'https://fin\.land\.naver\.com/complexes/[0-9]+', config['url']):
        raise ValueError('감시 주소는 https://fin.land.naver.com/complexes/숫자 형식이어야 합니다.')
    if type(config['intervalMinutes']) is not int or not 15 <= config['intervalMinutes'] <= 10080:
        raise ValueError('실행 간격은 15~10080분으로 입력하세요.')
    for key in ('scheduleEnabled', 'autoUpload'):
        if type(config[key]) is not bool:
            raise ValueError('설정 값 형식이 올바르지 않습니다.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', config['repository']):
        raise ValueError('GitHub 저장소는 owner/repository 형식으로 입력하세요.')
    if not re.fullmatch(r'[A-Za-z0-9_./-]{1,150}', config['branch']) or '..' in config['branch']:
        raise ValueError('GitHub 브랜치 이름을 확인하세요.')
    if not isinstance(config['githubToken'], str) or len(config['githubToken']) > 500:
        raise ValueError('GitHub 토큰 형식을 확인하세요.')
    if config['autoUpload'] and not config['githubToken']:
        raise ValueError('자동 업로드를 켜려면 GitHub 토큰을 저장하세요.')
    return config


def github(config, path, method='GET', data=None):
    if not config['githubToken']:
        raise ValueError('GitHub 토큰을 먼저 저장하세요.')
    headers = {'Authorization': 'Bearer ' + config['githubToken'], 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'whoga-nas', 'Content-Type': 'application/json'}
    request = Request('https://api.github.com/repos/' + config['repository'] + path,
                      headers=headers, method=method,
                      data=json.dumps(data).encode() if data is not None else None)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise ValueError(f'GitHub HTTP {exc.code}: 토큰 권한·저장소·브랜치 또는 기존 파일을 확인하세요.') from None
    except OSError:
        raise ValueError('GitHub 연결에 실패했습니다. NAS 인터넷 연결을 확인하세요.') from None


class App:
    def __init__(self, config_dir, output):
        self.config_dir, self.output = Path(config_dir), Path(output)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.config = validate(read(self.config_dir / 'settings.json', DEFAULT))
        self.state = read(self.output / 'dashboard.json', dict(running=False, upload={'status': 'not-configured'}))
        if self.state.get('running'):
            self.state.update(running=False, result='interrupted', message='컨테이너가 재시작됐습니다. 이전 실행은 성공으로 처리하지 않습니다.')
        if self.state.get('upload', {}).get('status') == 'running':
            self.state['upload'] = dict(status='failed', message='재시작으로 업로드 확인이 중단됐습니다. GitHub 파일을 확인하세요.')
        self.state['nextRun'] = time.time() + self.config['intervalMinutes'] * 60
        self.process = None
        self.cancelled = False
        self.log_path = self.output / 'current.log'
        self.save()

    def save(self):
        atomic(self.output / 'dashboard.json', self.state)

    def snapshot(self):
        with self.lock:
            config = {k: v for k, v in self.config.items() if k != 'githubToken'}
            config['tokenStored'] = bool(self.config['githubToken'])
            state = copy.deepcopy(self.state)
        logs = ''
        if self.log_path.exists():
            with self.log_path.open('rb') as f:
                f.seek(max(0, self.log_path.stat().st_size - 40000))
                logs = f.read(40000).decode('utf-8', errors='replace')
        # Defensive masking; collector itself never receives credentials.
        if self.config['githubToken']:
            logs = logs.replace(self.config['githubToken'], '[REDACTED]')
        return dict(config=config, state=state, log=logs)

    def settings(self, patch):
        with self.lock:
            if self.state['running'] or self.state.get('upload', {}).get('status') == 'running':
                raise ValueError('실행 또는 업로드가 끝난 뒤 설정을 변경하세요.')
            candidate = copy.deepcopy(self.config)
            for key in DEFAULT:
                if key in patch and (key != 'githubToken' or patch[key]):
                    candidate[key] = patch[key]
            if patch.get('clearToken'):
                candidate['githubToken'] = ''
            validate(candidate)
            atomic(self.config_dir / 'settings.json', candidate)
            self.config = candidate
            self.state['nextRun'] = time.time() + candidate['intervalMinutes'] * 60
            self.save()

    def start(self, mode):
        if mode not in ('smoke', 'probe', 'full'):
            raise ValueError('실행 모드를 확인하세요.')
        with self.lock:
            if self.state['running'] or self.state.get('upload', {}).get('status') == 'running':
                raise ValueError('이미 작업 중입니다.')
            config = copy.deepcopy(self.config)
            job = uuid.uuid4().hex
            self.cancelled = False
            self.state.update(running=True, jobId=job, mode=mode, startedAt=time.time(), result='running',
                              message='실행 중', lastResult=None, nextRun=time.time() + config['intervalMinutes'] * 60)
            self.log_path.write_text('')
            self.save()
            threading.Thread(target=self.worker, args=(mode, job, config), daemon=True).start()

    def worker(self, mode, job, config):
        folder = self.output / 'jobs' / job
        folder.mkdir(parents=True, exist_ok=True)
        result = None
        try:
            # A unique job directory prevents stale success files from being reused.
            with self.log_path.open('w') as log:
                with self.lock:
                    if self.cancelled:
                        raise ValueError('사용자가 실행을 중지했습니다.')
                    self.process = subprocess.Popen([sys.executable, str(ROOT / 'run.py'), mode,
                                                     '--url', config['url'], '--output', str(folder)],
                                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                                    env={k: v for k, v in os.environ.items() if k != 'DASHBOARD_PASSWORD'})
                try:
                    code = self.process.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait()
                    raise ValueError('30분 실행 제한으로 중지했습니다.')
            result = read(folder / 'status.json', {})
            if code != 0 or not result or self.cancelled:
                raise ValueError('수집에 실패하거나 중지됐습니다. 아래 로그를 확인하세요.')
            expected = {'smoke': 'browser-ready', 'probe': 'probe-passed', 'full': 'full-passed'}[mode]
            if result.get('status') != expected or result.get('url') != config['url']:
                raise ValueError('이번 실행 결과를 검증하지 못했습니다.')
            with self.lock:
                self.state.update(result=expected, message='검사가 완료됐습니다.', lastResult=result, successfulJob=job)
        except Exception as exc:
            with self.lock:
                self.state.update(result='failed', message=str(exc), lastResult=result)
        finally:
            if self.log_path.exists():
                shutil.copyfile(self.log_path, folder / 'run.log')
            with self.lock:
                self.process = None
                self.state.update(running=False, completedAt=time.time())
                self.save()
        if config['autoUpload'] and mode == 'full' and self.state['result'] == 'full-passed':
            try:
                self.start_upload()
            except ValueError:
                pass

    def stop(self):
        with self.lock:
            self.cancelled = True
            if self.process and self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGTERM)

    def start_upload(self):
        with self.lock:
            if self.state['running'] or self.state.get('upload', {}).get('status') == 'running':
                raise ValueError('이미 작업 중입니다.')
            result = self.state.get('lastResult') or {}
            if self.state.get('result') != 'full-passed' or result.get('url') != self.config['url']:
                raise ValueError('현재 감시 주소의 전체 수집이 성공한 뒤 업로드하세요.')
            if not self.config['githubToken']:
                raise ValueError('GitHub 토큰을 저장하세요.')
            job, run_id = self.state['successfulJob'], result['runId']
            if not re.fullmatch('[a-f0-9]{32}', job) or not re.fullmatch('[a-f0-9]{32}', run_id):
                raise ValueError('실행 식별자가 잘못됐습니다.')
            config = copy.deepcopy(self.config)
            upload_key = f"{config['repository']}:{config['branch']}:{run_id}"
            if self.state.get('upload', {}).get('key') == upload_key and self.state['upload'].get('status') == 'success':
                raise ValueError('이미 업로드한 실행입니다.')
            payload = read(self.output / 'jobs' / job / 'runs' / run_id / 'full.json', {})
            if (payload.get('mode') != 'full' or payload.get('runId') != run_id or
                    payload.get('target', {}).get('sourceUrl') != config['url'] or
                    payload.get('displayedCardCount') != payload.get('collectedCardCount') or
                    not payload.get('cards') or not payload.get('articles') or
                    len(payload['cards']) != payload.get('collectedCardCount') or
                    len(payload['articles']) != payload.get('articleCount')):
                raise ValueError('전체 수집 파일의 검증 항목이 일치하지 않습니다.')
            self.state['upload'] = dict(status='running', key=upload_key, at=time.time())
            self.save()
            threading.Thread(target=self.upload, args=(payload, config, upload_key), daemon=True).start()

    def upload(self, payload, config, key):
        path = 'nas-imports/' + config['url'].rsplit('/', 1)[1] + '/' + payload['runId'] + '.json'
        try:
            data = dict(message='data: add validated NAS collection ' + payload['runId'], branch=config['branch'],
                        content=base64.b64encode(json.dumps(payload, ensure_ascii=False, indent=2).encode()).decode())
            response = github(config, '/contents/' + path, 'PUT', data)
            upload = dict(status='success', key=key, path=path, at=time.time(),
                          url=response.get('content', {}).get('html_url', ''), message='검증 자료 업로드 완료 · 운영 앱 반영은 별도')
        except Exception as exc:
            upload = dict(status='failed', key=key, path=path, at=time.time(), message=str(exc))
        with self.lock:
            self.state['upload'] = upload
            self.save()

    def scheduler(self):
        while True:
            time.sleep(5)
            with self.lock:
                due = self.config['scheduleEnabled'] and not self.state['running'] and time.time() >= self.state['nextRun']
            if due:
                try:
                    self.start('full')
                except ValueError:
                    pass


def handler(app, password):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log headers or credentials.

        def reply(self, code, payload, mime='application/json'):
            body = json.dumps(payload, ensure_ascii=False).encode() if mime == 'application/json' else payload
            self.send_response(code)
            self.send_header('Content-Type', mime + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            expected = 'Basic ' + base64.b64encode(('admin:' + password).encode()).decode()
            if hmac.compare_digest(self.headers.get('Authorization', ''), expected):
                return True
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="WhoGa NAS", charset="UTF-8"')
            self.send_header('Content-Length', '0')
            self.end_headers()
            return False

        def do_GET(self):
            if self.path == '/health':
                return self.reply(200, {'status': 'ok'})
            if not self.authorized():
                return
            if self.path == '/api/status':
                return self.reply(200, app.snapshot())
            assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
            if self.path in assets:
                name, mime = assets[self.path]
                return self.reply(200, (ROOT / 'static' / name).read_bytes(), mime)
            return self.reply(404, {'error': '찾을 수 없습니다.'})

        def do_POST(self):
            if not self.authorized():
                return
            origin = self.headers.get('Origin')
            if self.headers.get('X-Whoga-Request') != '1' or (origin and urlsplit(origin).netloc != self.headers.get('Host')):
                return self.reply(403, {'error': '요청 출처를 확인할 수 없습니다.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 65536:
                    raise ValueError('요청 크기가 올바르지 않습니다.')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('설정 형식이 올바르지 않습니다.')
                if self.path == '/api/settings':
                    app.settings(data)
                elif self.path == '/api/run':
                    app.start(data.get('mode'))
                elif self.path == '/api/stop':
                    app.stop()
                elif self.path == '/api/upload':
                    app.start_upload()
                elif self.path == '/api/github-test':
                    with app.lock:
                        config = copy.deepcopy(app.config)
                    github(config, '/branches/' + quote(config['branch'], safe=''))
                    return self.reply(200, {'message': '저장소·브랜치 읽기 확인 완료. 쓰기 권한은 실제 업로드 때 확인합니다.'})
                else:
                    return self.reply(404, {'error': '찾을 수 없습니다.'})
                return self.reply(200, {'message': '요청을 처리했습니다.'})
            except (ValueError, TypeError, KeyError) as exc:
                return self.reply(400, {'error': str(exc)})
            except Exception:
                return self.reply(500, {'error': '처리 오류: 폴더 권한 또는 서버 로그를 확인하세요.'})
    return Handler


def main():
    password = os.environ.get('DASHBOARD_PASSWORD', '')
    if len(password) < 12:
        raise SystemExit('DASHBOARD_PASSWORD를 12자 이상 설정하세요.')
    app = App(os.environ.get('WHOGA_CONFIG_DIR', '/config'), os.environ.get('WHOGA_OUTPUT_DIR', '/output'))
    threading.Thread(target=app.scheduler, daemon=True).start()
    server = ThreadingHTTPServer(('0.0.0.0', 8899), handler(app, password))
    print('WhoGa NAS dashboard ready on port 8899', flush=True)
    try:
        server.serve_forever()
    finally:
        app.stop()


if __name__ == '__main__':
    main()
