"""NAS-only validation collector; never publishes WhoGa production data."""
import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import sys
import uuid
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnostics import BrowserEvents, capture_run, clean, write_json
from version import build_info
from browser_control import wait_for_desktop

SOURCE = Path(__file__).resolve().parents[1] / 'experiments/supplied-v2/collector.py'
spec = importlib.util.spec_from_file_location('supplied', SOURCE)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
URL = 'https://fin.land.naver.com/complexes/140635'


def sequence(mode, stage):
    stage('probe')
    if mode == 'full':
        stage('full')


def choose_page(context, url):
    requested = urlsplit(url)
    for page in context.pages:
        current = urlsplit(page.url)
        if (current.scheme, current.netloc, current.path.rstrip('/')) == (requested.scheme, requested.netloc, requested.path.rstrip('/')):
            return page
    return next((page for page in context.pages if urlsplit(page.url).hostname == requested.hostname),
                context.pages[0] if context.pages else context.new_page())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['smoke', 'browse', 'probe', 'full', 'compare'], nargs='?', default='probe')
    parser.add_argument('--output', default='/output')
    parser.add_argument('--url', default=URL)
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'https://fin\.land\.naver\.com/complexes/[0-9]+', args.url):
        parser.error('단지 주소 https://fin.land.naver.com/complexes/숫자 를 입력하세요.')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    # Kernel releases this lock even after container termination.
    with (output / '.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another NAS collection is running.', file=sys.stderr)
            return 2
        run_id = uuid.uuid4().hex
        run_dir = output / 'runs' / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        status = dict(runId=run_id, startedAt=collector.now(), url=args.url,
                      mode=args.mode, runner='nas-docker', publicationEligible=False,
                      build=build_info(), status='running')
        phases, page, events = [], None, None
        saved = False

        def step(name, details=None):
            status['phase'] = name
            event = clean(dict(phase=name, at=collector.now(), **(details or {})))
            phases.append(event)
            write_json(run_dir / 'status.json', status)
            print(json.dumps(event, ensure_ascii=False), flush=True)

        def fail(error):
            status.update(status='failed', failedPhase=status.get('phase', 'browser-connect'),
                          error=clean(str(error)), errorType=type(error).__name__)

        def finish():
            nonlocal saved
            try:
                if args.mode != 'compare':
                    capture_run(page, run_dir, status, phases, events, Path('/output/browser-diagnostics.json'))
            except Exception as error:
                # A failed diagnostic must never turn a failed collection into success.
                status['diagnosticsError'] = clean(str(error))
            status['completedAt'] = collector.now()
            write_json(run_dir / 'status.json', status)
            write_json(output / 'status.json', status)
            saved = True
            print(json.dumps(status, ensure_ascii=False), file=sys.stderr if status['status'] == 'failed' else sys.stdout)

        step('browser-connect')
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                if args.mode == 'compare':
                    from comparison import compare
                    try:
                        report = compare(pw, args.url, run_dir, status, step)
                        status['status'] = 'comparison-complete'
                        status['stoppedReason'] = report.get('stoppedReason')
                    except Exception as error:
                        fail(error)
                    finish()
                    return 1 if status['status'] == 'failed' else 0
                try:
                    # This is the same persistent, visible browser shown by noVNC.
                    wait_for_desktop()
                    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222', timeout=15000)
                    context = browser.contexts[0]
                    page = choose_page(context, args.url)
                    events = BrowserEvents(context)
                    status['browserVersion'] = browser.version
                    page.bring_to_front()
                    if args.mode == 'smoke':
                        step('smoke-browser')
                        page.screenshot(path=str(output / 'browser-smoke.png'), timeout=10000)
                        status['status'] = 'browser-ready'
                    elif args.mode == 'browse':
                        step('browse-document')
                        response = page.goto(args.url + '?tab=article&articleTradeTypes=A1', wait_until='commit', timeout=180000)
                        status['documentStatus'] = response.status if response else None
                        if not response or response.status >= 400:
                            # A native browser may have committed headers while the old
                            # document is still being replaced. Capture the error document.
                            try:
                                page.wait_for_load_state('domcontentloaded', timeout=5000)
                            except Exception:
                                pass
                            raise RuntimeError('원문 문서 응답을 확인하지 못했습니다.')
                        # Opening a document is not a successful collection.
                        status['status'] = 'page-opened'
                    else:
                        def stage(mode):
                            progress = lambda name, details: step(mode + ':' + name, details)
                            raw, expected, counts, final_url, target = collector.collect(
                                page, args.url, probe=(mode == 'probe'), progress=progress,
                                navigation_url=args.url + '?tab=article&articleTradeTypes=A1')
                            step(mode + ':normalize')
                            groups, articles = collector.normalize(raw, len(raw) if mode == 'probe' else expected,
                                                                  target['complexName'], target['estateTypeText'])
                            result = dict(schemaVersion='nas-experiment-1', runId=run_id, target=target,
                                          collectedAt=collector.now(), mode=mode, displayedCardCount=expected,
                                          collectedCardCount=len(groups), articleCount=len(articles),
                                          observedCardCounts=counts, finalUrl=final_url,
                                          publicationEligible=False, cards=groups, articles=articles)
                            collector.atomic_json(run_dir / (mode + '.json'), result)
                            status[mode] = dict(status='passed', cards=len(groups), articles=len(articles))
                        sequence(args.mode, stage)
                        status['status'] = args.mode + '-passed'
                except Exception as error:
                    fail(error)
                finally:
                    finish()  # Capture before disconnecting; leave the Chrome window open.
        except Exception as error:
            if not saved:
                fail(error)
                finish()
        return 1 if status['status'] == 'failed' else 0


if __name__ == '__main__':
    sys.exit(main())
