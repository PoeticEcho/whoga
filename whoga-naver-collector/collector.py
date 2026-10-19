"""Exact-map collection. No publication, direct API replay, stealth or proxy fallback."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from monitor import ValidationError, atomic_json, now_kst, parse_raw_text, validate_snapshot
PANEL = (HERE/'panel.js').read_text()
DEFAULT_URL = (HERE/'target-url.txt').read_text().strip()
CONFIG = json.loads((ROOT/'config.json').read_text())


def digest(value):
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def target_url(value=''):
    value = value or DEFAULT_URL
    p = urlsplit(value)
    q = parse_qs(p.query, keep_blank_values=True)
    if (p.scheme != 'https' or p.netloc != 'fin.land.naver.com' or p.path != '/map'
            or p.fragment or any(c.isspace() for c in value)
            or not all(len(q.get(k, [])) == 1 and q[k][0] for k in ('center','zoom','layer','tradeTypes','realEstateTypes'))
            or q['tradeTypes'] != ['A1'] or q['realEstateTypes'] != ['A02']):
        raise ValidationError('Only HTTPS Naver map / A1 / A02 with complete parameters is supported')
    return value  # Do not rewrite or decode the layer/center strings.


class Accumulator:
    """One key per displayed GROUP, never one per brokerage article."""
    def __init__(self):
        self.rows = {}
        self.total = None
        self.observations = 0
        self.repeats = 0
        self.full_stable = 0
        self.previous_signature = None

    def feed(self, state):
        if state.get('blocked') or state.get('notFound'):
            raise ValidationError('source-access-restricted' if state.get('blocked') else 'source-not-found')
        n = state.get('declaredCount')
        if not state.get('sourceReady') or not isinstance(n,int) or isinstance(n,bool) or n <= 0:
            self.full_stable = 0
            return False
        if self.total is not None and self.total != n:
            raise ValidationError('source-total-changed')
        self.total = n
        if not all(state.get('scope',{}).get(k) for k in ('sale','allAreas','allBuildings')):
            raise ValidationError('source-filter-scope-not-confirmed')
        local = set()
        for row in state['rows']:
            _, items = parse_raw_text(row['text'], CONFIG['allowedDongs'])
            if len(items) != 1:
                raise ValidationError('unparsed-source-card')
            item = items[0]
            # Text fingerprint is only a within-run group key. It is NOT an article number.
            key = 'group-' + digest(row['text'])
            if key in local:
                raise ValidationError('ambiguous-identical-group-cards')
            local.add(key)
            self.observations += 1
            if key in self.rows:
                self.repeats += 1
            item.update(id=key,articleId=None)
            self.rows[key] = {'key':key,'text':row['text'],'item':item,
                'representativeArticleId':row.get('representativeArticleId'),
                'grouped':bool(row.get('grouped'))}
        if state['cardCount'] != len(state['rows']):
            raise ValidationError('dom-card-count-mismatch')
        if len(self.rows) > n:
            raise ValidationError('collected-more-than-declared')
        signature = digest(self.rows)
        full = len(self.rows) == n and state.get('atBottom') and not state.get('loading')
        self.full_stable = self.full_stable+1 if full and signature == self.previous_signature else (1 if full else 0)
        self.previous_signature = signature
        return self.full_stable >= 2


def collect_page(page, report, directory=None):
    from playwright.sync_api import TimeoutError as BrowserTimeout
    report['stage'] = 'navigation'
    response = page.goto(report['source_url'], wait_until='commit', timeout=45000)
    report['document_status'] = response.status if response else None
    if not response or response.status != 200:
        raise ValidationError('document-http-error')
    report['stage'] = 'article-tab'
    page.get_by_role('tab',name='매물',exact=True).click(timeout=20000)
    report['stage'] = 'scroll'
    passes = []
    deadline = time.monotonic()+240
    for pass_no in (1,2):
        if pass_no == 2:
            page.evaluate(PANEL, 'top')
        acc = Accumulator()
        for step in range(240):
            if time.monotonic() > deadline:
                raise ValidationError('scroll-time-limit')
            page.wait_for_timeout(1000)
            state = page.evaluate(PANEL, False)
            report['view'] = state['viewport']
            complete = acc.feed(state)
            report['visible_total_count'] = acc.total
            report['unique_collected_count'] = len(acc.rows)
            event = {'pass':pass_no,'step':step,'total':acc.total,'unique':len(acc.rows),
                'dom':state['cardCount'],'at_bottom':state['atBottom'],'scroll_top':state['scrollTop']}
            report['progress'].append(event)
            if directory:
                atomic_json(directory/'validation.json',report)
                atomic_json(directory/'raw-cards.json',{'run_id':report['run_id'],
                    'source_url':report['source_url'],'source_url_sha256':report['source_url_sha256'],
                    'collected_at':now_kst(),'status':'partial','cards':list(acc.rows.values())})
            if step == 0 or len(report['progress']) < 2 or event['unique'] != report['progress'][-2]['unique']:
                print(json.dumps(event), flush=True)
            if complete:
                passes.append(acc)
                break
            if state.get('panelFound'):
                page.evaluate(PANEL, 'next')
        else:
            raise ValidationError('scroll-step-limit')
    if passes[0].total != passes[1].total or passes[0].rows != passes[1].rows:
        raise ValidationError('full-pass-content-changed')
    report.update(duplicate_count=0, repeated_observations=sum(a.repeats for a in passes),
        raw_observation_count=sum(a.observations for a in passes), terminal_confirmed=True,
        identical_complete_passes=2, identity_method='within-run-group-text-sha256',
        identity_limit='Grouped cards are not individual brokerage IDs; identical cards fail closed.')
    return list(passes[-1].rows.values())


@contextmanager
def browser_page(transport, region, report):
    from playwright.sync_api import sync_playwright
    if transport == 'local':
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                report['browser_version'] = browser.version
                page = browser.new_page(viewport={'width':1440,'height':900},locale='ko-KR')
                yield page
            finally:
                browser.close()
        return
    import requests
    key = os.environ.get('BROWSERBASE_API_KEY')
    if not key:
        raise ValidationError('missing-browserbase-secret')
    headers = {'X-BB-API-Key':key,'Content-Type':'application/json'}
    session = None
    try:
        report['stage'] = 'session-create'
        response = requests.post('https://api.browserbase.com/v1/sessions', headers=headers,
            json={'timeout':360,'keepAlive':False,'region':region,'proxies':False,
                'browserSettings':{'viewport':{'width':1440,'height':900},'solveCaptchas':False,
                    'advancedStealth':False,'ignoreCertificateErrors':False,'recordSession':False,'logSession':False}},
            timeout=(10,30),allow_redirects=False)
        report['session_create_status'] = response.status_code
        if response.status_code != 201:
            raise ValidationError('browserbase-plan-or-quota' if response.status_code in (402,403,429) else 'browserbase-session-error')
        session = response.json()
        report['region'] = session.get('region',region)
        with sync_playwright() as p:
            report['stage'] = 'browser-connect'
            browser = p.chromium.connect_over_cdp(session['connectUrl'],timeout=30000)
            report['browser_version'] = browser.version
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.set_viewport_size({'width':1440,'height':900})
            yield page
    finally:
        if session:
            try:
                released = requests.post('https://api.browserbase.com/v1/sessions/'+session['id'],headers=headers,
                    json={'status':'REQUEST_RELEASE'},timeout=(10,15),allow_redirects=False)
                report['session_release_status'] = released.status_code
            except Exception:
                report['session_release_status'] = 'request-failed-server-timeout-bounded'


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--transport',choices=['local','browserbase'],default='local')
    parser.add_argument('--region',choices=['us-west-2','us-east-1','eu-central-1','ap-southeast-1'],default='ap-southeast-1')
    parser.add_argument('--output',type=Path,default=ROOT/'collector-runs')
    args=parser.parse_args(argv)
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:10]
    directory=args.output/run_id
    directory.mkdir(parents=True,exist_ok=False)
    report={'run_id':run_id,'started_at':now_kst(),'status':'fail','completeness':'unknown',
        'stage':'resolve-target','transport':args.transport,'progress':[],
        'visible_total_count':None,'unique_collected_count':0,'duplicate_count':None,
        'missing_count':None,'publication':'not-attempted','view':{'width':1440,'height':900}}
    try:
        url=target_url(os.environ.get('MANUAL_URL',''))
        report.update(source_url=url,source_url_sha256=digest(url),default_target=url==DEFAULT_URL)
        with browser_page(args.transport,args.region,report) as page:
            rows=collect_page(page,report,directory)
        report['collected_at']=now_kst()
        report['stage']='validate'
        snapshot={'date':report['collected_at'][:10],'declaredCount':report['visible_total_count'],
            'items':[r['item'] for r in rows]}
        validate_snapshot(snapshot,require_complete=True,allowed_dongs=CONFIG['allowedDongs'])
        raw={'run_id':run_id,'source_url':url,'source_url_sha256':digest(url),'collected_at':report['collected_at'],'cards':rows}
        atomic_json(directory/'raw-cards.json',raw)
        report.update(status='pass',completeness='verified',stage='complete',missing_count=0,raw_sha256=digest(raw))
        atomic_json(directory/'dictionaries.json',{'run_id':run_id,'allowed_dongs':CONFIG['allowedDongs'],
            'types':{'168OB':'78OB','180OA':'84OA'},'unit':'displayed-group-card'})
    except Exception as exc:
        report['error_type']=type(exc).__name__
        # Signed remote URLs, cookies and secrets must never enter evidence or logs.
        report['reason']=str(exc) if isinstance(exc,ValidationError) else 'external-operation-failed'
        match=re.search(r'net::ERR_[A-Z_]+',str(exc))
        if match: report['network_error']=match[0]
    finally:
        report['finished_at']=now_kst()
        atomic_json(directory/'validation.json',report)
        if output:=os.environ.get('GITHUB_OUTPUT'):
            with open(output,'a') as f:f.write(f'run_dir={directory.relative_to(ROOT) if directory.is_relative_to(ROOT) else directory}\nrun_id={run_id}\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ('progress','source_url')},ensure_ascii=False,indent=2))
    return 0 if report['status']=='pass' else 1

if __name__=='__main__':
    raise SystemExit(main())
