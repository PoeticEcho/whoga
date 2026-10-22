#!/usr/bin/env python3
"""Observe the public listing panel with a visible Playwright browser under Xvfb.

This uses normal browser input and accessibility reads, not the OpenAI CUA API.
Access restrictions stop collection; incomplete data never replaces a snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import urlopen

from monitor import (ROOT, ValidationError, atomic_json, fingerprint, now_kst,
                     parse_raw_text, read_json, record_failure, save_snapshot,
                     validate_snapshot)

READ_PANEL_JS = """
() => {
  const headline = [...document.querySelectorAll("h3")].find(e => /매물\\s*[\\d,]+\\s*개/.test(e.innerText));
  const panel = [...document.querySelectorAll('[class*="ScrollBox"][class*="scroller"]')].find(e => headline && e.contains(headline));
  if (!panel) return {sourceReady:false,reason:"listing-panel-not-found",text:document.body ? document.body.innerText : ""};
  const text = panel.innerText;
  const match = text.match(/매물\\s*([\\d,]+)\\s*개/);
  const rect = panel.getBoundingClientRect();
  return {
    sourceReady:Boolean(headline && /오피스텔/.test(text)),
    declaredCount:match ? Number(match[1].replaceAll(",","")) : null,
    cardCount:(text.match(/(?:수성범어더블유|수성범어W)\\s*\\d+동/g)||[]).length,
    scrollTop:panel.scrollTop,scrollHeight:panel.scrollHeight,clientHeight:panel.clientHeight,
    atBottom:panel.scrollTop+panel.clientHeight>=panel.scrollHeight-8,
    rect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},
    text
  };
}
"""


def validate_target(url, config):
    target, expected = urlsplit(url), urlsplit(config['sourceUrl'])
    if (target.scheme != 'https' or target.netloc != expected.netloc
            or target.path != expected.path or target.fragment
            or parse_qs(target.query, keep_blank_values=True)
            != parse_qs(expected.query, keep_blank_values=True)):
        raise ValidationError('대상 URL은 config.json의 단지·매매 목록과 같아야 합니다.')
    return url


def guard_page(state):
    text = state.get('text', '')
    if any(term in text for term in ('비정상적인 접근', '접근이 제한', '서비스 이용이 제한',
                                    '자동입력 방지', '로봇이 아닙니다', 'CAPTCHA',
                                    '페이지를 찾을 수 없습니다', '로그인이 필요')):
        raise ValidationError('접근 제한·인증 또는 오류 화면입니다. 우회하지 않고 중단합니다.')


def wait_for_panel(page, cdp, report, evidence_dir, *, timeout_seconds=300):
    """Keep the loaded tab open while map scripts and the listing panel initialize."""
    started = time.monotonic()
    checkpoints = iter((30, 60, 120, 180, 240, 300))
    next_checkpoint = next(checkpoints, None)
    report['stage'] = 'panel-loading'
    timeline = report.setdefault('loadingTimeline', [])
    while True:
        elapsed = time.monotonic() - started
        cdp.send('Accessibility.getFullAXTree', {'depth': 2})
        state = page.evaluate(READ_PANEL_JS)
        guard_page(state)
        observation = {
            'elapsedSeconds': round(elapsed, 1),
            'sourceReady': bool(state.get('sourceReady')),
            'declaredCount': state.get('declaredCount'),
            'cardCount': state.get('cardCount', 0),
        }
        timeline.append(observation)
        report['panelWaitSeconds'] = observation['elapsedSeconds']
        print('초기 화면 대기: ' + json.dumps(observation, ensure_ascii=False), flush=True)
        if next_checkpoint is not None and elapsed >= next_checkpoint:
            try:
                page.screenshot(path=str(evidence_dir / f'loading-{next_checkpoint}s.png'), timeout=5000)
            except Exception:
                pass
            next_checkpoint = next(checkpoints, None)
        if state.get('sourceReady') and (state.get('declaredCount') or 0) > 0 and state.get('cardCount', 0) > 0:
            return
        if elapsed >= timeout_seconds:
            raise ValidationError(f'문서 접속 후 {timeout_seconds:g}초 동안 기다렸지만 매물 패널이 준비되지 않았습니다. 기존 자료를 유지합니다.')
        page.wait_for_timeout(min(5000, max(1, (timeout_seconds - elapsed) * 1000)))


def collect_panel(page, cdp, config, report, *, max_reads=100):
    """Require two identical complete reads at the panel bottom, including parsing."""
    initial_total, previous_fingerprint = None, None
    stable_reads, bottom_stalls, previous_count = 0, 0, None
    deadline = time.monotonic() + 180
    for attempt in range(max_reads):
        if time.monotonic() >= deadline:
            break
        page.wait_for_timeout(1400)
        cdp.send('Accessibility.getFullAXTree', {'depth': 2})
        state = page.evaluate(READ_PANEL_JS)
        guard_page(state)
        total, count = state.get('declaredCount'), state.get('cardCount', 0)
        if initial_total is not None and total != initial_total:
            raise ValidationError('수집 도중 원문 총수가 변경되거나 패널을 잃었습니다. 기존 자료를 유지합니다.')
        ready = state.get('sourceReady') and isinstance(total, int) and total > 0
        items, parsed_total = [], None
        if ready:
            initial_total = total
            parsed_total, items = parse_raw_text(state['text'], config['allowedDongs'])
        full = bool(ready and state.get('atBottom') and parsed_total == total == count == len(items))
        snapshot = {'date': now_kst()[:10], 'declaredCount': total, 'items': items}
        current_fingerprint = None
        if full:
            validate_snapshot(snapshot, require_complete=True, allowed_dongs=config['allowedDongs'])
            current_fingerprint = fingerprint(snapshot)
            stable_reads = stable_reads + 1 if current_fingerprint == previous_fingerprint else 1
        else:
            stable_reads = 0
        previous_fingerprint = current_fingerprint
        report.update(declaredCount=total, cardCount=count, parsedCount=len(items),
                      atBottom=bool(state.get('atBottom')), stableReads=stable_reads)
        progress = {key: report[key] for key in ('declaredCount', 'cardCount', 'parsedCount', 'atBottom', 'stableReads')}
        report.setdefault('reads', []).append(progress)
        if not report.setdefault('scrollCounts', []) or report['scrollCounts'][-1] != count:
            report['scrollCounts'].append(count)
        print(json.dumps(progress, ensure_ascii=False), flush=True)
        if stable_reads == 2:
            report['observedAt'] = now_kst()
            snapshot['observation'] = {
                'transport': 'playwright-headed-xvfb', 'observedAt': report['observedAt'],
                'scrollCounts': report['scrollCounts'], 'stableReads': 2,
                'declaredCount': total, 'cardCount': count, 'atBottom': True,
            }
            return snapshot
        if not ready:
            if attempt >= 14:
                raise ValidationError('초기 로딩 후 매물 패널을 확인하지 못했습니다. 기존 자료를 유지합니다.')
            continue
        bottom_stalls = bottom_stalls + 1 if state.get('atBottom') and count == previous_count and not full else 0
        previous_count = count
        if bottom_stalls >= 5:
            break
        if full:
            continue  # Read again without moving once completeness is reached.
        rect = state['rect']
        x, y = rect['x'] + rect['width'] / 2, rect['y'] + rect['height'] * .6
        viewport = page.viewport_size
        if (not all(math.isfinite(value) for value in (x, y, rect['width'], rect['height']))
                or rect['width'] <= 0 or rect['height'] <= 0
                or not (0 <= x < viewport['width'] and 0 <= y < viewport['height'])):
            raise ValidationError('매물 패널의 휠 입력 좌표가 화면 밖입니다.')
        page.mouse.move(round(x), round(y))
        for _ in range(12):
            page.mouse.wheel(0, 140)
            page.wait_for_timeout(60)
    raise ValidationError(f"전체 목록 검증 실패: 원문 {report.get('declaredCount')} / 카드 {report.get('cardCount')} / 해석 {report.get('parsedCount')}건. 기존 자료를 유지합니다.")


def collect_browser(config, target_url, evidence_dir, report, *, headless=False, executable=None,
                    navigation_timeout=180, panel_timeout=300):
    from playwright.sync_api import sync_playwright
    if not headless and not os.environ.get('DISPLAY'):
        raise ValidationError('가상 화면이 없습니다. xvfb-run으로 실행해 주세요.')
    with sync_playwright() as p:
        options = {'headless': headless}
        if executable:
            options['executable_path'] = executable
        browser = p.chromium.launch(**options)
        report.update(browserVersion=browser.version,
                      browserExecutable=Path(executable).name if executable else 'playwright-chromium')
        print(f"브라우저: {report['browserExecutable']} · {report['browserVersion']}", flush=True)
        try:
            context = browser.new_context(viewport={'width': 1280, 'height': 900},
                                          locale='ko-KR', timezone_id='Asia/Seoul')
            failures = report.setdefault('requestFailures', [])

            def note_failure(request):
                if len(failures) < 30:
                    url = urlsplit(request.url)
                    failures.append({'host': url.hostname, 'path': url.path,
                                     'type': request.resource_type, 'error': request.failure})

            context.on('requestfailed', note_failure)
            http_errors = report.setdefault('httpErrors', [])

            def note_response(response):
                if response.status >= 400 and len(http_errors) < 30:
                    url = urlsplit(response.url)
                    http_errors.append({'host': url.hostname, 'path': url.path, 'status': response.status})

            context.on('response', note_response)
            # Create the working tab once; keep it open throughout slow map loading.
            initial = context.new_page()
            page = context.new_page()
            initial.close()
            try:
                report.update(stage='document-commit', navigationTimeoutSeconds=navigation_timeout)
                # Receipt of the document and completion of dynamic map scripts
                # have separate budgets. Do not wait for ads or networkidle here.
                response = page.goto(target_url, wait_until='commit', timeout=navigation_timeout * 1000)
                if not response or response.status >= 400:
                    raise ValidationError(f'원문 HTTP 응답 실패: {response.status if response else "없음"}. 수집을 중단합니다.')
                report.update(documentStatus=response.status, documentReceivedAt=now_kst())
                if urlsplit(page.url).netloc != urlsplit(target_url).netloc:
                    raise ValidationError('원문이 인증 또는 다른 사이트로 이동했습니다. 수집을 중단합니다.')
                cdp = context.new_cdp_session(page)
                wait_for_panel(page, cdp, report, evidence_dir, timeout_seconds=panel_timeout)
                report['stage'] = 'panel-scroll'
                snapshot = collect_panel(page, cdp, config, report)
                if headless:
                    snapshot['observation']['transport'] = 'playwright-headless-diagnostic'
                return snapshot
            finally:
                try:
                    report['pageTitle'] = page.title()
                    report['pageExcerpt'] = page.locator('body').inner_text(timeout=3000)[:1000]
                except Exception:
                    pass
                try:
                    page.screenshot(path=str(evidence_dir / 'last-screen.png'), timeout=5000)
                except Exception:
                    pass  # Screenshot availability does not alter validation.
        finally:
            browser.close()


def attempt_evidence(report):
    # Keep this attempt separate from the preserved last-success counts.
    keys = ('attemptAt', 'observedAt', 'stage', 'errorType', 'errorDetail', 'message',
            'declaredCount', 'cardCount', 'parsedCount', 'atBottom', 'stableReads',
            'scrollCounts', 'requestFailures', 'httpErrors', 'pageTitle', 'pageExcerpt',
            'navigationTimeoutSeconds', 'documentStatus', 'documentReceivedAt',
            'panelWaitSeconds', 'loadingTimeline', 'browserVersion', 'browserExecutable')
    return {key: report[key] for key in keys if key in report}


def persist_snapshot(data_dir, snapshot, report=None):
    """Prepare all JSONs before replacing files; Git publishes the three together."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    names = [snapshot['date'][:10] + '.json', 'index.json', 'status.json']
    original = {name: (data_dir / name).read_bytes() if (data_dir / name).exists() else None for name in names}
    with tempfile.TemporaryDirectory(prefix='.cua-stage-', dir=data_dir.parent) as temp:
        stage = Path(temp)
        for path in data_dir.glob('*.json'):
            shutil.copy2(path, stage / path.name)
        save_snapshot(stage, snapshot, source_kind='naver-live')
        if report is not None:
            status = read_json(stage / 'status.json')
            status['lastAttemptEvidence'] = attempt_evidence(report)
            atomic_json(stage / 'status.json', status)
        try:
            for name in names:
                os.replace(stage / name, data_dir / name)
        except Exception:
            for name, content in original.items():
                if content is None:
                    (data_dir / name).unlink(missing_ok=True)
                else:
                    (data_dir / name).write_bytes(content)
            raise


def write_summary(report):
    outcome = '성공' if report['ok'] else '실패 · 기존 자료 보존'
    lines = ['### 1. 매물 수집·JSON 검증', f'- 결과: **{outcome}**',
             f"- 브라우저: {report.get('browserExecutable', '시작 전')} · {report.get('browserVersion', '미확인')}",
             f"- 확인 시각: {report.get('observedAt', report['attemptAt'])} (KST)",
             f"- 원문 / 카드 / 해석: {report.get('declaredCount', '—')} / {report.get('cardCount', '—')} / {report.get('parsedCount', '—')}",
             f"- 하단: {report.get('atBottom', False)} · 연속 일치: {report.get('stableReads', 0)}회",
             f"- 스크롤 수량: {' → '.join(map(str, report.get('scrollCounts', []))) or '미확인'}",
             f"- 문서 HTTP: {report.get('documentStatus', '미수신')} · 패널 로딩 대기: {report.get('panelWaitSeconds', 0)}초",
             f"- JSON 저장: {'완료' if report.get('saved') else '하지 않음'}"]
    if report.get('message'):
        lines.append(f"- 사유: {report['message']}")
        lines.append(f"- 실패 단계: {report['stage']} · 유형: {report.get('errorType', '미확인')}")
    output = '\n'.join(lines) + '\n'
    print(output)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as handle:
            handle.write(output)


def verify_site(site_url, site_dir, *, attempts=12, delay=5):
    """Compare deployed HTML, index, status and every indexed JSON byte for byte."""
    site_dir = Path(site_dir)
    index = read_json(site_dir / 'data/index.json')
    paths = ['index.html', 'data/index.json', 'data/status.json'] + ['data/' + row['file'] for row in index['snapshots']]
    expected = {path: hashlib.sha256((site_dir / path).read_bytes()).digest() for path in paths}
    last_error = None
    for attempt in range(attempts):
        try:
            for path, digest in expected.items():
                url = site_url.rstrip('/') + '/' + quote(path) + '?verify=' + str(time.time_ns())
                with urlopen(url, timeout=15) as response:
                    if response.status != 200 or hashlib.sha256(response.read()).digest() != digest:
                        raise ValidationError(f'공개 데이터 불일치: {path}')
            print(f'Pages 공개 파일 일치: 화면·상태·목록·스냅샷 {len(index["snapshots"])}개')
            return
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(delay)
    raise ValidationError('Pages 공개 파일이 이번 배포 결과와 일치하지 않습니다.') from last_error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data')
    parser.add_argument('--evidence-dir', type=Path, default=ROOT / 'test-results/cua')
    parser.add_argument('--target-url', default=os.environ.get('TARGET_URL', ''))
    parser.add_argument('--headless', action='store_true', help='로컬 진단용. Actions는 Xvfb headed 사용')
    parser.add_argument('--browser-executable', default=os.environ.get('BROWSER_EXECUTABLE'))
    parser.add_argument('--dry-run', action='store_true', help='검증만 수행. data/ 변경 없음')
    parser.add_argument('--navigation-timeout', type=int, default=180, help='최초 문서 응답 대기 초 (기본 180)')
    parser.add_argument('--panel-timeout', type=int, default=300, help='문서 수신 후 매물 패널 대기 초 (기본 300)')
    parser.add_argument('--verify-site', help='배포 후 공개 파일 대조만 수행')
    parser.add_argument('--site-dir', type=Path, default=ROOT / '_site')
    args = parser.parse_args(argv)
    if args.navigation_timeout <= 0 or args.panel_timeout <= 0:
        parser.error('대기 시간은 0보다 커야 합니다.')
    if args.verify_site:
        verify_site(args.verify_site, args.site_dir)
        return 0
    report = {'ok': False, 'saved': False, 'attemptAt': now_kst(), 'stage': 'initial-load'}
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    try:
        config = read_json(ROOT / 'config.json')
        target_url = validate_target(args.target_url or config['sourceUrl'], config)
        snapshot = collect_browser(config, target_url, args.evidence_dir, report,
                                   headless=args.headless, executable=args.browser_executable,
                                   navigation_timeout=args.navigation_timeout, panel_timeout=args.panel_timeout)
        if not args.dry_run:
            report['stage'] = 'save-json'
            persist_snapshot(args.data_dir, snapshot, report)
            report['saved'] = True
        report.update(ok=True, stage='complete')
    except Exception as exc:
        report['errorType'] = type(exc).__name__
        report['errorDetail'] = str(exc).split('Call log:')[0].strip()[:600]
        report['message'] = str(exc) if isinstance(exc, ValidationError) else '브라우저 연결 또는 저장에 실패했습니다. 실행 로그와 증거 파일을 확인해 주세요.'
        print(f"수집 실패 ({type(exc).__name__}): {exc}", file=sys.stderr)
        if not args.dry_run:
            record_failure(args.data_dir, report['message'])
            status = read_json(args.data_dir / 'status.json')
            status['lastAttemptEvidence'] = attempt_evidence(report)
            atomic_json(args.data_dir / 'status.json', status)
    finally:
        atomic_json(args.evidence_dir / 'report.json', report)
        write_summary(report)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
