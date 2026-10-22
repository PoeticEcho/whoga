"""NAS-only validation collector; never publishes WhoGa production data."""
import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import sys
import uuid

SOURCE = Path(__file__).resolve().parents[1] / 'experiments/supplied-v2/collector.py'
spec = importlib.util.spec_from_file_location('supplied', SOURCE)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)
URL = 'https://fin.land.naver.com/complexes/140635'


def sequence(mode, stage):
    stage('probe')
    if mode == 'full':
        stage('full')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['smoke', 'browse', 'probe', 'full'], nargs='?', default='probe')
    parser.add_argument('--output', default='/output')
    parser.add_argument('--url', default=URL)
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'https://fin\.land\.naver\.com/complexes/[0-9]+', args.url):
        parser.error('단지 주소 https://fin.land.naver.com/complexes/숫자 를 입력하세요.')
    from playwright.sync_api import sync_playwright
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
        status = dict(runId=run_id, startedAt=collector.now(), url=args.url,
                      mode=args.mode, runner='nas-docker', publicationEligible=False)
        phase = 'browser-launch'
        try:
            with sync_playwright() as pw:
                # This is the same persistent, visible browser shown by noVNC.
                # Stopping this client disconnects CDP without stopping Chrome.
                browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222', timeout=15000)
                context = browser.contexts[0]
                page = context.pages[0] if context.pages else context.new_page()
                page.bring_to_front()
                try:
                    if args.mode == 'smoke':
                        page.screenshot(path=str(output / 'browser-smoke.png'), timeout=10000)
                        status['browserVersion'] = browser.version
                        status['status'] = 'browser-ready'
                    elif args.mode == 'browse':
                        response = page.goto(args.url, wait_until='commit', timeout=180000)
                        if not response or response.status >= 400:
                            raise RuntimeError('원문 문서 응답을 확인하지 못했습니다.')
                        # Opening a document is not a successful collection.
                        status['status'] = 'page-opened'
                    else:
                        def stage(mode):
                            nonlocal phase
                            phase = mode
                            try:
                                raw, expected, counts, final_url, target = collector.collect(page, args.url, probe=(mode == 'probe'))
                                groups, articles = collector.normalize(raw, len(raw) if mode == 'probe' else expected,
                                                                      target['complexName'], target['estateTypeText'])
                                result = dict(schemaVersion='nas-experiment-1', runId=run_id, target=target,
                                              collectedAt=collector.now(), mode=mode, displayedCardCount=expected,
                                              collectedCardCount=len(groups), articleCount=len(articles),
                                              observedCardCounts=counts, finalUrl=final_url,
                                              publicationEligible=False, cards=groups, articles=articles)
                                collector.atomic_json(run_dir / (mode + '.json'), result)
                                status[mode] = dict(status='passed', cards=len(groups), articles=len(articles))
                            finally:
                                try:
                                    page.screenshot(path=str(run_dir / (mode + '-screen.png')), timeout=5000)
                                except Exception:
                                    pass
                        sequence(args.mode, stage)
                        status['status'] = args.mode + '-passed'
                finally:
                    pass  # Keep the desktop window available for inspection.
        except Exception as exc:
            status.update(status='failed', failedPhase=phase, error=str(exc), completedAt=collector.now())
            collector.atomic_json(run_dir / 'status.json', status)
            collector.atomic_json(output / 'status.json', status)
            print(json.dumps(status, ensure_ascii=False), file=sys.stderr)
            return 1
        status['completedAt'] = collector.now()
        collector.atomic_json(run_dir / 'status.json', status)
        collector.atomic_json(output / 'status.json', status)
        print(json.dumps(status, ensure_ascii=False))
        return 0


if __name__ == '__main__':
    sys.exit(main())
