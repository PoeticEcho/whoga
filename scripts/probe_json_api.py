"""One bounded request to the exact public JSON example in BiohPark/naverland.

This only diagnoses the example's response on GitHub's runner. Its regional
apartment markers are never treated as the target officetel's listing snapshot.
No cookies, authentication, direct API paging, retries, or redirects are used.
"""
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor import now_kst
from scripts.probe_map import structural_summary


def main():
    import requests
    config = json.loads((ROOT/'config/api-probe.json').read_text())
    target = urlsplit(config['url'])
    if target.scheme != 'https' or target.netloc != 'new.land.naver.com' or target.path != '/api/complexes/single-markers/2.0':
        raise ValueError('Expected the reference repository public example URL')
    report = {'startedAt': now_kst(), 'scope': config['scope'], 'path': target.path,
              'reference': config['reference'], 'fullComplexEligible': False,
              'productionFilesChanged': False, 'stage': 'starting'}
    started = time.monotonic()
    try:
        with requests.get(config['url'], headers=config['headers'], timeout=(10, 20),
                          stream=True, allow_redirects=False) as response:
            report.update(status=response.status_code,
                          contentType=response.headers.get('content-type', '').split(';')[0],
                          firstResponseSeconds=round(time.monotonic()-started, 2))
            if response.is_redirect:
                location = urlsplit(response.headers.get('location', ''))
                report.update(stage='redirect-not-json', redirectHost=location.hostname, redirectPath=location.path)
            elif response.status_code in (401, 403, 429):
                report['stage'] = 'http-access-response'
            elif response.status_code != 200:
                report['stage'] = 'http-error'
            else:
                body = bytearray()
                for chunk in response.iter_content(16384):
                    body.extend(chunk)
                    if len(body) > 2_000_000:
                        report['stage'] = 'response-size-limit'
                        break
                else:
                    try:
                        payload = json.loads(body)
                        report.update(stage='json-response-received', structure=structural_summary(payload))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        report['stage'] = 'response-is-not-json'
    except requests.exceptions.ConnectTimeout:
        report['stage'] = 'connection-timeout'
    except requests.exceptions.ReadTimeout:
        report['stage'] = 'first-response-timeout'
    except requests.exceptions.RequestException as exc:
        report.update(stage='request-error', errorType=type(exc).__name__)
    report.update(finishedAt=now_kst(), totalSeconds=round(time.monotonic()-started, 2))
    directory = ROOT/'probe-results'
    directory.mkdir(exist_ok=True)
    (directory/'json-api-probe.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    if summary := os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(summary, 'a') as handle:
            handle.write('## JSON API 직접 요청 시험\n\n원본 예제의 지역 단지 마커 응답만 검사합니다. whoga 자료를 변경하지 않습니다.\n\n```json\n')
            handle.write(json.dumps(report, ensure_ascii=False, indent=2)+'\n```\n')
    return 0 if report['stage'] == 'json-response-received' else 1


if __name__ == '__main__':
    raise SystemExit(main())
