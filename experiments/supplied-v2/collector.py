#!/usr/bin/env python3
"""네이버 단지 매매: URL 기반 목록/묶음 수집 및 호환성 점검.

설치: python -m pip install playwright && python -m playwright install chromium
실행: python collector.py --url-file target-url.txt --output data
실제 창이 있는 환경이 기본이며, 서버에서는 --headless를 명시합니다.
"""
import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import urlparse, parse_qs

KST = timezone(timedelta(hours=9))
CARDS = 'ul[class*="ComplexArticleTab"][class*="__article"] > li'
EXTRACT = r'''els => els.map((el, index) => {
  const data = el.firstElementChild;
  const t = (root, selector) => root.querySelector(selector)?.textContent.trim() || null;
  const id = root => root.querySelector('a[class*="__link"]')?.getAttribute('href')?.match(/^\/articles\/(\d+)(?:\/|\?|$)/)?.[1] || null;
  const group = t(data, '[class*="__text-more"]');
  return {
    index, name: t(data, '[class*="__name"]'),
    priceText: t(data, 'span[class*="__price"]'),
    summary: Array.from(data.querySelectorAll('[class*="__item-summary"]')).map(x => x.textContent.trim()),
    badge: t(data, '[data-sentry-component="PropertyBadgeList"]'),
    agentCount: group ? Number(group.match(/\d+/)?.[0]) : null,
    articleNo: group ? null : id(data),
    articles: Array.from(el.querySelectorAll('[data-sentry-component="ArticleCardSub"]')).map(s => ({
      articleNo: id(s), priceText: t(s, 'span[class*="__price"]'),
      badge: t(s, '[data-sentry-component="PropertyBadgeList"]')
    }))
  };
})'''


def now():
    return datetime.now(KST).isoformat(timespec='seconds')


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def price_won(text):
    text = re.sub(r'변동.*$', '', text or '')
    text = re.sub(r'^매매\s*', '', text or '').replace(',', '').strip()
    match = re.fullmatch(r'(?:(\d+)억)?\s*(\d+)?(?:만(?:원)?)?', text)
    if not match or not any(match.groups()):
        raise ValueError('해석할 수 없는 가격: ' + text)
    return int(match[1] or 0) * 100_000_000 + int(match[2] or 0) * 10_000


def price_range(text):
    values = [price_won(part) for part in (text or '').split('~')]
    if not 1 <= len(values) <= 2 or values != sorted(values):
        raise ValueError('잘못된 가격 범위: ' + str(text))
    return min(values), max(values)


def normalize(cards, expected, complex_name=None, estate_type=None):
    if expected <= 0 or len(cards) != expected:
        raise ValueError(f'카드 불완전: {len(cards)} / 화면 {expected}')
    articles = {}
    groups = []
    count_differences = []
    for position, card in enumerate(cards):
        if card['index'] != position:
            raise ValueError('카드 순서/누락 오류')
        if complex_name and not (card['name'] == complex_name or (card['name'] or '').startswith(complex_name + ' ')):
            raise ValueError('대상 단지 불일치')
        summary = card['summary']
        if len(summary) != 4 or summary[0] not in ('아파트', '오피스텔') or not (card['priceText'] or '').startswith('매매 '):
            raise ValueError('지원 유형(아파트/오피스텔) 또는 매매 필터/필드 불일치')
        if estate_type and summary[0] != estate_type:
            raise ValueError('단지 내 유형 혼합: 별도 검토 필요')
        low, high = price_range(card['priceText'])
        members = card['articles'] if card['agentCount'] is not None else [card]
        if not members:
            raise ValueError(f'{position}번 묶음이 펼쳐지지 않았습니다')
        member_ids = []
        for member in members:
            article_id = member['articleNo']
            if not article_id or not re.fullmatch(r'\d+', article_id):
                raise ValueError(f'{position}번 카드 매물번호 누락')
            if not (member['priceText'] or '').startswith('매매 '):
                raise ValueError('개별 매물 거래유형 불일치')
            minimum, maximum = price_range(member['priceText'])
            if minimum < low or maximum > high:
                raise ValueError(f'{position}번 카드의 대표/개별 호가 불일치')
            if article_id in articles:
                raise ValueError(f'중복 매물번호: {article_id}')
            date_match = re.search(r'\d{4}\.\d{2}\.\d{2}', member['badge'] or '')
            articles[article_id] = {
                'articleNo': article_id, 'cardIndex': position,
                'name': card['name'], 'priceText': member['priceText'],
                'priceMinWon': minimum, 'priceMaxWon': maximum,
                'areaText': summary[1], 'floorInfo': summary[2], 'direction': summary[3],
                'badgeText': member['badge'],
                'displayDate': date_match[0] if date_match else None,
                'sourceUrl': f'https://fin.land.naver.com/articles/{article_id}'
            }
            member_ids.append(article_id)
        if card['agentCount'] is not None and card['agentCount'] != len(members):
            count_differences.append({'cardIndex': position, 'uiAgentCount': card['agentCount'], 'articleCount': len(members)})
        groups.append({
            'cardIndex': position, 'name': card['name'], 'priceText': card['priceText'],
            'priceMinWon': low, 'priceMaxWon': high, 'summary': summary,
            'uiAgentCount': card['agentCount'], 'groupedArticleCount': len(members) if card['agentCount'] is not None else None,
            'sameAddressCount': None, 'articleNos': member_ids
        })
    # 현재 UI에서 수량이 일치함을 실측했으므로, 바뀌면 자동 배포를 중단합니다.
    # 중개사 수와 매물 수가 본질적으로 같다는 뜻은 아닙니다.
    if count_differences:
        raise ValueError('묶음 수량 재검토 필요: ' + json.dumps(count_differences, ensure_ascii=False))
    return groups, list(articles.values())


def check_block(page):
    text = page.locator('body').inner_text(timeout=15000)
    if re.search(r'verify you are human|checking your browser|unusual traffic|자동화된 접근|비정상적인 접근|접근이 제한|보안 확인|로봇이 아닙니다', text, re.I):
        raise RuntimeError('접근/인증 확인 화면입니다. 자동 재시도 없이 중단합니다.')


def parse_header_count(text):
    match = re.match(r'^\s*매물\s*([\d,]+)', text)
    if not match:
        raise ValueError('매물 목록 제목의 건수를 확인할 수 없습니다: ' + text)
    return int(match[1].replace(',', ''))


def header_count(page):
    # Some layouts render "매물 121" without the former "개" suffix.
    # Only the selected complex's list heading is authoritative, never "매매 121".
    title = page.locator('#complex_detail').get_by_role('heading', name=re.compile(r'^매물\s*[\d,]+'))
    text = title.inner_text(timeout=30000)
    return parse_header_count(text)


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'fin.land.naver.com':
        raise ValueError('https://fin.land.naver.com URL이 필요합니다')
    complex_match = re.fullmatch(r'/complexes/(\d+)/?', parsed.path)
    if complex_match:
        return complex_match[1]
    if parsed.path.rstrip('/') == '/map' and parse_qs(parsed.query).get('layer'):
        return None
    raise ValueError('단지 /complexes/숫자 URL 또는 단지를 선택한 /map?layer=... URL이 필요합니다')


def collect(page, url, probe=False, sample_cards=3, progress=None):
    def step(name, **details):
        if progress:
            progress(name, details)

    step('navigation')
    requested_id = validate_url(url)
    # A user may already have opened this complex in the visible NAS browser.
    # Preserve its loading progress instead of discarding the tab and session.
    current, requested = urlparse(page.url), urlparse(url)
    if (current.scheme, current.netloc, current.path.rstrip('/')) != (requested.scheme, requested.netloc, requested.path.rstrip('/')):
        response = page.goto(url, wait_until='commit', timeout=180000)
        if not response or response.status >= 400:
            raise RuntimeError('원문 문서 HTTP 응답 실패. 기존 결과를 유지합니다.')
    step('complex-panel')
    panel = page.locator('#complex_detail')
    panel.wait_for(state='visible', timeout=300000)
    check_block(page)
    complex_name = panel.get_by_role('heading', level=3).first.inner_text().strip()
    step('sale-filter')
    sale = panel.get_by_role('button', name=re.compile(r'^매매\s*[\d,]+$'))
    sale.wait_for(state='visible', timeout=30000)
    # 단지 URL의 기본 전체거래유형 및 지도 바깥쪽 필터와 구별합니다.
    sale.click()
    panel.locator('button[id="거래유형"]').wait_for(state='visible', timeout=30000)
    page.wait_for_function('''() => document.querySelector('#complex_detail button[id="거래유형"]')?.textContent.trim() === '매매' ''', timeout=30000)
    step('complex-identity')
    tab = panel.get_by_role('tab', name=re.compile(r'^매물(?:\s*현재 위치)?$'))
    href = tab.get_attribute('href') or ''
    match = re.search(r'/complexes/(\d+)', href)
    if not match or (requested_id and match[1] != requested_id):
        raise ValueError('화면에서 단지번호를 확인할 수 없거나 URL과 다릅니다')
    complex_id = match[1]
    step('list-count')
    expected = header_count(page)
    if expected <= 0:
        raise ValueError('매매 0건: 로딩/실제 0건 구별이 필요하므로 자동 저장하지 않습니다')
    step('first-cards', displayedCount=expected)
    cards = page.locator(CARDS)
    cards.first.wait_for(timeout=30000)
    page.wait_for_function('''selector => {
      const els = [...document.querySelectorAll(selector)];
      return els.length > 0 && els.every(el => el.querySelector('span[class*="__price"]')?.textContent.startsWith('매매 '));
    }''', arg=CARDS, timeout=30000)
    expected = header_count(page)
    observed_counts = [cards.count()]
    metadata = {'complexNo': complex_id, 'complexName': complex_name, 'tradeType': 'A1',
                'sourceUrl': url, 'scope': 'selected-complex-sale-with-current-panel-filters',
                'panelFilters': panel.locator('button[id]').evaluate_all('(els) => els.map(el => ({id:el.id,text:el.textContent.trim()}))')}
    # 실제 스크롤 대상은 window가 아니라 #complex_detail입니다.
    for _ in range(100):
        current = cards.count()
        if probe or current >= expected:
            break
        step('scroll-list', loadedCards=current, displayedCount=expected)
        cards.last.scroll_into_view_if_needed()
        panel.evaluate('(el) => {el.scrollTop += Math.max(200, el.clientHeight / 2);}')
        try:
            page.wait_for_function('(p) => document.querySelectorAll(p.selector).length > p.count',
                                   arg={'selector': CARDS, 'count': current}, timeout=20000)
        except Exception:
            check_block(page)
            raise RuntimeError(f'추가 페이지 로드 중단: {current}/{expected}')
        observed_counts.append(cards.count())
        time.sleep(1)
    if not probe and cards.count() != expected:
        raise RuntimeError('화면 건수와 로드된 카드 수가 다릅니다')
    limit = min(sample_cards, cards.count()) if probe else expected
    results = []
    for index in range(limit):
        step('extract-card', cardIndex=index, sampleSize=limit)
        check_block(page)
        card = cards.nth(index)
        expand = card.get_by_role('button', name='매물목록 펼치기')
        grouped = expand.count() > 0
        if grouped:
            step('expand-group', cardIndex=index)
            expand.click()
            card.locator('[data-sentry-component="ArticleCardSub"]').first.wait_for(state='attached', timeout=20000)
            # UI가 알리는 묶음 수량까지 기다리고, 부분 응답은 성공으로 저장하지 않습니다.
            wanted = int(re.search(r'\d+', card.locator('[class*="__text-more"]').inner_text())[0])
            deadline = time.monotonic() + 20
            while card.locator('[data-sentry-component="ArticleCardSub"]').count() < wanted:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f'{index}번 묶음 부분 로딩')
                time.sleep(.5)
        row = card.evaluate('(el) => (' + EXTRACT + ')([el])[0]')
        row['index'] = index
        results.append(row)
        if grouped:
            card.get_by_role('button', name='매물목록 접기').click()
        print(f'카드 {index + 1}/{limit} (화면 총 {expected})', flush=True)
        time.sleep(1)
    step('verify-counts', extractedCards=len(results), displayedCount=expected)
    if header_count(page) != expected or (not probe and cards.count() != expected):
        raise RuntimeError('수집 도중 목록 건수가 변경되었습니다')
    metadata['estateTypeText'] = results[0]['summary'][0]
    return results, expected, observed_counts, page.url, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--url')
    source.add_argument('--url-file')
    parser.add_argument('--output', default='data')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--probe', action='store_true', help='처음 3개 카드의 호환성 검사만 수행; latest 미갱신')
    parser.add_argument('--sample-cards', type=int, default=3)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    lock = output / '.collector.lock'
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        print('다른 수집이 실행 중이거나 이전 실행의 잠금이 남아 있습니다.', file=sys.stderr)
        return 2
    os.close(lock_fd)
    started = now()
    try:
        if not 1 <= args.sample_cards <= 10:
            raise ValueError('--sample-cards는 1~10 범위여야 합니다')
        url = args.url or Path(args.url_file or 'target-url.txt').read_text(encoding='utf-8').strip()
        validate_url(url)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=args.headless)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='ko-KR')
                raw, expected, counts, final_url, metadata = collect(page, url, args.probe, args.sample_cards)
            finally:
                browser.close()
        run_id = datetime.now(KST).strftime('%Y%m%dT%H%M%S')
        target_output = output / metadata['complexNo']
        atomic_json(target_output / 'history' / (run_id + '-raw.json'), raw)
        groups, articles = normalize(raw, len(raw) if args.probe else expected, metadata['complexName'], metadata['estateTypeText'])
        result = {
            'schemaVersion': '2.0.0', 'source': 'naver-land', 'startedAt': started, 'collectedAt': now(),
            'target': metadata,
            'collection': {'status': 'probe-passed' if args.probe else 'validated-ui-snapshot',
                           'mode': 'browser-dom', 'displayedCardCount': expected, 'visibleCardCount': len(groups),
                           'articleCount': len(articles), 'groupCount': sum(c['uiAgentCount'] is not None for c in groups),
                           'observedCardCounts': counts, 'hasUnfetchedPages': args.probe, 'finalUrl': final_url,
                           'limitations': ['수집 시간 동안 매물 변경 가능', '개별 상세 페이지 내부 필드 미수집', '기존 whoga 스키마 연결 별도 필요']},
            'cards': groups, 'articles': articles
        }
        atomic_json(target_output / 'history' / (run_id + '.json'), result)
        atomic_json(target_output / ('probe.json' if args.probe else 'latest.json'), result)
        atomic_json(output / 'status.json', {'status': 'probe-passed' if args.probe else 'success', 'startedAt': started, 'completedAt': now(), 'target': metadata, 'articleCount': len(articles)})
        print(f'성공: 카드 {len(groups)}, 개별 매물 {len(articles)}')
        return 0
    except Exception as exc:
        atomic_json(output / 'status.json', {'status': 'failed', 'startedAt': started, 'failedAt': now(), 'error': str(exc), 'latestPreserved': True})
        print(f'실패: {exc}. 기존 latest.json은 유지합니다.', file=sys.stderr)
        return 1
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    sys.exit(main())
