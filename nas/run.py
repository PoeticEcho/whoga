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
    parser.add_argument('mode', choices=['smoke', 'probe', 'full'], nargs='?', default='probe')
    parser.add_argument('--output', default='/output')
    args = parser.parse_args()
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
        status = dict(runId=run_id, startedAt=collector.now(), url=URL,
                      mode=args.mode, runner='nas-docker', publicationEligible=False)
        phase = 'browser-launch'
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, chromium_sandbox=True)
                try:
                    if args.mode == 'smoke':
                        page = browser.new_page()
                        page.set_content('<title>whoga-smoke</title><p>browser ready</p>')
                        assert page.title() == 'whoga-smoke'
                        page.close()
                        status['status'] = 'browser-ready'
                    else:
                        def stage(mode):
                            nonlocal phase
                            phase = mode
                            page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='ko-KR')
                            try:
                                raw, expected, counts, final_url, target = collector.collect(page, URL, probe=(mode == 'probe'))
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
                                page.close()
                        sequence(args.mode, stage)
                        status['status'] = args.mode + '-passed'
                finally:
                    browser.close()
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
