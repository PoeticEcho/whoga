"""Bounded ordinary remote-browser trial; never log credentials or CDP URLs."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor import now_kst, parse_raw_text, validate_snapshot, save_snapshot
from scripts.probe_map import PANEL_SCRIPT, terminal_page


def run_probe(report):
    import requests
    from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout, Error as BrowserError

    key = os.environ.get('BROWSERBASE_API_KEY')
    if not key:
        report['stage'] = 'missing-secret'
        return None
    config = json.loads((ROOT / 'config.json').read_text())
    headers = {'X-BB-API-Key': key, 'Content-Type': 'application/json'}
    session_id = None
    browser = None
    try:
        report['stage'] = 'creating-session'
        response = requests.post('https://api.browserbase.com/v1/sessions', headers=headers,
            json={'timeout': 180, 'keepAlive': False, 'proxies': False,
                  'browserSettings': {'viewport': {'width': 1280, 'height': 1000},
                      'solveCaptchas': False, 'advancedStealth': False,
                      'ignoreCertificateErrors': False, 'recordSession': False, 'logSession': False}},
            timeout=(10, 30), allow_redirects=False)
        report['sessionCreateStatus'] = response.status_code
        if response.status_code != 201:
            report['stage'] = 'session-create-failed'
            return None
        session = response.json()
        session_id = session['id']
        report['sessionCreated'] = True
        with sync_playwright() as p:
            report['stage'] = 'connecting-browser'
            browser = p.chromium.connect_over_cdp(session['connectUrl'], timeout=30000)
            report['browserConnected'] = True
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(10000)
            report['stage'] = 'opening-naver'
            started = time.monotonic()
            try:
                response = page.goto(config['sourceUrl'], wait_until='commit', timeout=45000)
            except BrowserTimeout:
                report.update(stage='first-response-timeout', navigationSeconds=round(time.monotonic()-started, 2))
                return None
            except BrowserError as exc:
                # Whitelist the Chromium network error identifier only. The
                # surrounding message may contain signed connection details.
                code = re.search(r'net::ERR_[A-Z_]+', str(exc))
                report.update(stage='navigation-error',
                              navigationErrorCode=code.group(0) if code else 'unclassified-browser-error',
                              navigationSeconds=round(time.monotonic()-started, 2))
                return None
            report.update(documentStatus=response.status if response else None,
                          navigationSeconds=round(time.monotonic()-started, 2))
            if response and response.status in (401, 403, 429):
                report['stage'] = 'http-access-response'
                return None
            expected, previous, stalls, stable = None, None, 0, 0
            for _ in range(45):
                page.wait_for_timeout(1200)
                state = page.evaluate(PANEL_SCRIPT, False)
                if terminal := terminal_page(state['text']):
                    report['stage'] = terminal
                    return None
                declared, items = parse_raw_text(state['text'], config['allowedDongs'])
                progress = {k: state[k] for k in ('declaredCount', 'cardCount', 'panelFound', 'atBottom')}
                progress['parsedCount'] = len(items)
                if not report['progress'] or progress != report['progress'][-1]:
                    report['progress'].append(progress)
                    print('Listing progress: ' + json.dumps(progress), flush=True)
                report.update(declaredCount=declared, parsedCount=len(items), cardCount=state['cardCount'])
                if declared and declared > 0:
                    if expected is not None and declared != expected:
                        report['stage'] = 'declared-count-changed'
                        return None
                    expected = declared
                complete = (state['sourceReady'] and expected and
                            expected == declared == state['cardCount'] == len(items))
                # Two identical complete observations, not just two equal counts.
                stable = stable + 1 if complete and items == previous else (1 if complete else 0)
                if stable >= 2:
                    observed = now_kst()
                    snapshot = {'date': observed[:10], 'declaredCount': expected, 'items': items,
                                'observedAt': observed, 'transport': 'browserbase-cdp'}
                    quality = validate_snapshot(snapshot, require_complete=True, allowed_dongs=config['allowedDongs'])
                    for item in items:
                        if not re.fullmatch(r'[\d저중고]+/\d+층', item['floor']):
                            report['stage'] = 'invalid-floor'
                            return None
                        if not re.fullmatch(r'(?:남서|남동|북서|북동|서|동|남|북)향', item['direction']):
                            report['stage'] = 'invalid-direction'
                            return None
                    report.update(stage='complete', observedAt=observed, validation=quality,
                                  buildings=dict(Counter(x['dong'] for x in items)), stableReads=stable)
                    return snapshot
                stalls = stalls + 1 if state['atBottom'] and items and items == previous else 0
                if stalls >= 5:
                    report['stage'] = 'incomplete-at-bottom'
                    return None
                previous = items
                if state['panelFound'] and state['sourceReady'] and not complete:
                    page.evaluate(PANEL_SCRIPT, True)
            report['stage'] = 'loading-or-scroll-limit'
            return None
    finally:
        # keepAlive=false also terminates on disconnect. Explicit release covers
        # connection failures; the 180-second server timeout is a final bound.
        if session_id:
            try:
                released = requests.post(f'https://api.browserbase.com/v1/sessions/{session_id}',
                    headers=headers, json={'status': 'REQUEST_RELEASE'}, timeout=(10, 15), allow_redirects=False)
                report['sessionReleaseStatus'] = released.status_code
            except Exception as exc:
                report['releaseErrorType'] = type(exc).__name__
        # The Playwright manager closes its transport on leaving the with block.


def main():
    report = {'startedAt': now_kst(), 'transport': 'browserbase-cdp', 'progress': [],
              'productionFilesChanged': False, 'stage': 'starting'}
    try:
        snapshot = run_probe(report)
        if snapshot:
            # Trial branch only. Production promotion is a separate verified step.
            save_snapshot(ROOT / 'data', snapshot, source_kind='naver-live')
            report['candidateSaved'] = True
    except Exception as exc:
        report.update(failedStage=report['stage'], stage='probe-error', errorType=type(exc).__name__)
        # Exception strings can contain a signed connection URL. Never print them.
    report['finishedAt'] = now_kst()
    output = ROOT / 'probe-results'
    output.mkdir(exist_ok=True)
    (output / 'browserbase-probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(summary, 'a') as handle:
            handle.write('## Browserbase full-list trial\n\n```json\n'+json.dumps(report, ensure_ascii=False, indent=2)+'\n```\n')
    return 0 if report['stage'] == 'complete' and report.get('candidateSaved') else 1


if __name__ == '__main__':
    raise SystemExit(main())
