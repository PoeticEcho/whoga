"""Read-only browser evidence. No cookies, authentication headers or API bodies."""
from collections import Counter, deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from version import build_info
from resources import resource_snapshot

SAFE_QUERY = {'tab', 'articleTradeTypes', 'page', 'pageSize', 'complexNo', 'tradeType'}


def safe_url(value):
    try:
        parts = urlsplit(value)
        if parts.scheme in ('data', 'blob'):
            return parts.scheme + ':[omitted]'
        if parts.scheme not in ('http', 'https'):
            return value[:500]
        host = parts.hostname or ''
        if parts.port:
            host += ':' + str(parts.port)
        query = urlencode([(k, v if k in SAFE_QUERY else '[redacted]') for k, v in parse_qsl(parts.query)])
        return urlunsplit((parts.scheme, host, parts.path, query, ''))[:2000]
    except ValueError:
        return '[invalid URL]'


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'https?://[^\s<>"\x27]+', lambda m: safe_url(m[0]), value)
        value = re.sub(r'(?:github_pat_|gh[upsohr]_)[A-Za-z0-9_]+', '[redacted-token]', value)
        value = re.sub(r'Bearer\s+\S+', 'Bearer [redacted]', value, flags=re.I)
        return value[:8000]
    return value


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(clean(value), stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class BrowserEvents:
    def __init__(self, context):
        self.events = deque(maxlen=120)
        self.totals = Counter()
        self.sessions = []
        self.dirty = True
        context.on('response', self.response)
        context.on('requestfailed', self.request_failed)
        context.on('page', self.attach_page)
        for page in context.pages:
            self.attach_page(page)

    def add(self, kind, **details):
        if 'ERR_INSUFFICIENT_RESOURCES' in str(details.get('failure', '')) + str(details.get('text', '')):
            self.totals['insufficientResourcesErrors'] += 1
        if ((kind == 'browser-blocked' and details.get('blockedReason') == 'csp') or
                (kind == 'csp-violation' and not details.get('reportOnly'))):
            self.totals['cspBlocks'] += 1
        self.events.append(clean(dict(at=time.time(), kind=kind, **details)))
        self.dirty = True

    def response(self, response):
        resource = response.request.resource_type
        self.totals[resource + 'Responses'] += 1
        self.dirty = True
        headers = response.headers
        csp = headers.get('content-security-policy')
        report_only = headers.get('content-security-policy-report-only')
        parts = urlsplit(response.url)
        listing_api = (parts.hostname == 'fin.land.naver.com' and '/front-api/' in parts.path and
                       parts.path.rsplit('/', 1)[-1] in ('list', 'mount', 'recentView', 'legalDivisionView'))
        if resource == 'document' or listing_api or response.status >= 400 or csp or report_only:
            self.add('http-response', url=safe_url(response.url), resourceType=resource,
                     status=response.status, csp=csp, cspReportOnly=report_only,
                     contentType=headers.get('content-type'))

    def request_failed(self, request):
        self.totals['failedRequests'] += 1
        self.add('request-failed', url=safe_url(request.url), resourceType=request.resource_type,
                 failure=request.failure)

    def attach_page(self, page):
        page.on('console', lambda message: self.add('console-error', pageUrl=safe_url(page.url), text=message.text)
                if message.type == 'error' else None)
        page.on('pageerror', lambda error: self.add('javascript-error', pageUrl=safe_url(page.url), text=str(error)))
        try:
            session = page.context.new_cdp_session(page)
            self.sessions.append(session)
            requests = {}

            def requested(event):
                requests[event['requestId']] = safe_url(event['request']['url'])
                if len(requests) > 300:
                    requests.pop(next(iter(requests)))

            def failed(event):
                url = requests.pop(event['requestId'], None)
                if event.get('blockedReason'):
                    self.add('browser-blocked', pageUrl=safe_url(page.url), url=url,
                             blockedReason=event['blockedReason'], resourceType=event.get('type'))

            def issue(event):
                details = event.get('issue', {}).get('details', {}).get('contentSecurityPolicyIssueDetails')
                if details:
                    self.add('csp-violation', pageUrl=safe_url(page.url),
                             blockedUrl=safe_url(details.get('blockedURL', '')),
                             directive=details.get('violatedDirective'), reportOnly=details.get('isReportOnly'),
                             violationType=details.get('contentSecurityPolicyViolationType'))

            session.on('Network.requestWillBeSent', requested)
            session.on('Network.loadingFailed', failed)
            session.on('Network.loadingFinished', lambda event: requests.pop(event['requestId'], None))
            session.on('Audits.issueAdded', issue)
            session.send('Network.enable')
            session.send('Audits.enable')
        except Exception as error:
            self.add('diagnostic-error', operation='attach-cdp-audits', error=str(error))

    def snapshot(self):
        return dict(events=list(self.events), totals=dict(self.totals))

    def persist(self, path):
        if self.dirty:
            write_json(path, dict(build=build_info(), capturedAt=time.time(), resources=resource_snapshot(), **self.snapshot()))
            self.dirty = False


PAGE_SNAPSHOT = r'''(() => {
  const visible = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const panel = document.querySelector('#complex_detail');
  const headingTexts = root => [...root.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]')]
    .filter(visible).slice(0,30).map(el => el.textContent.trim());
  return {
    url: location.href, title: document.title, readyState: document.readyState,
    bodyText: /https?:/.test(location.protocol) ? (document.body?.innerText || '').slice(0,6000) : '',
    panelPresent: Boolean(panel), headings: headingTexts(document), panelHeadings: panel ? headingTexts(panel) : [],
    panelTabs: panel ? [...panel.querySelectorAll('a[role="tab"]')].slice(0,20).map(el => ({
      href: el.href, text: el.textContent.trim().slice(0,200), selected: el.getAttribute('aria-selected'),
      ariaHidden: Boolean(el.closest('[aria-hidden="true"]')), visible: visible(el)
    })) : [],
    panelScroll: panel ? {top: panel.scrollTop, height: panel.clientHeight, contentHeight: panel.scrollHeight} : null,
    cardCount: document.querySelectorAll('ul[class*="ComplexArticleTab"][class*="__article"] > li').length,
    saleFilter: panel?.querySelector('button[id="거래유형"]')?.textContent.trim() || null,
    metaCsp: [...document.querySelectorAll('meta[http-equiv]')]
      .filter(el => el.httpEquiv.toLowerCase() === 'content-security-policy').map(el => el.content),
    environment: {userAgent: navigator.userAgent, language: navigator.language, languages: navigator.languages,
      userAgentData: navigator.userAgentData?.toJSON(), platform: navigator.platform,
      hardwareConcurrency: navigator.hardwareConcurrency, deviceMemory: navigator.deviceMemory,
      maxTouchPoints: navigator.maxTouchPoints, screen: {width: screen.width, height: screen.height},
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone, webdriver: navigator.webdriver,
      viewport: {width: innerWidth, height: innerHeight}, devicePixelRatio,
      mobile: navigator.userAgentData?.mobile ?? /Mobile|iPhone|Android/.test(navigator.userAgent)}
  };
})()'''


def page_snapshot(page):
    session = page.context.new_cdp_session(page)
    try:
        result = session.send('Runtime.evaluate', dict(expression=PAGE_SNAPSHOT, returnByValue=True, timeout=2000))
        if result.get('exceptionDetails'):
            raise RuntimeError(result['exceptionDetails'].get('text', 'Page inspection failed'))
        value = result['result']['value']
        value['url'] = safe_url(value['url'])
        return clean(value)
    finally:
        session.detach()


def classify(snapshot, events, totals=None):
    text = snapshot.get('bodyText', '')
    title = snapshot.get('title', '')
    if re.search(r'verify you are human|unusual traffic|자동화된 접근|비정상적인 접근|접근이 제한|보안 확인|로봇이 아닙니다', text, re.I):
        state = 'access-or-verification-screen'
    elif re.search(r'\b(?:404|500|502|503)\b|페이지를 찾을 수 없|에러|오류|error', title, re.I) or re.search(r'페이지를 찾을 수 없|서비스에 접속할 수 없', text):
        state = 'error-screen'
    elif snapshot.get('cardCount', 0) > 0:
        state = 'listing-cards-visible'
    elif snapshot.get('environment', {}).get('mobile') and not snapshot.get('panelPresent'):
        state = 'mobile-layout-without-desktop-panel'
    elif snapshot.get('panelPresent') or re.search(r'로딩|loading', text, re.I):
        state = 'loading-or-empty-list'
    else:
        state = 'unexpected-or-unavailable-page'
    csp = bool((totals or {}).get('cspBlocks')) or any((e['kind'] == 'browser-blocked' and e.get('blockedReason') == 'csp') or
              (e['kind'] == 'csp-violation' and not e.get('reportOnly')) for e in events)
    exhausted = bool((totals or {}).get('insufficientResourcesErrors')) or any(
        'ERR_INSUFFICIENT_RESOURCES' in str(e.get('failure', '')) + str(e.get('text', '')) for e in events)
    return dict(pageState=state, cspBlockedDuringRun=csp, resourceFailureDuringRun=exhausted,
                javascriptErrorDuringRun=any(e['kind'] == 'javascript-error' for e in events))


def capture_run(page, run_dir, status, phases, events, history_path):
    run_dir = Path(run_dir)
    report = dict(runId=status['runId'], build=status['build'], mode=status['mode'],
                  status=status.get('status'), startedAt=status.get('startedAt'),
                  probe=status.get('probe'), full=status.get('full'),
                  phase=status.get('phase'), phases=phases, error=status.get('error'),
                  browserVersion=status.get('browserVersion'), capturedAt=datetime.now(timezone.utc).isoformat(),
                  duringRun=events.snapshot() if events else {'events': [], 'totals': {}}, artifacts={})
    snapshot = {}
    if page is not None:
        try:
            snapshot = page_snapshot(page)
        except Exception as error:
            report['inspectionError'] = str(error)
        # The CDP read is bounded, as is the independent screenshot attempt.
        name = re.sub(r'[^a-z0-9-]', '-', status.get('phase', status['mode'])) + '.png'
        try:
            page.screenshot(path=str(run_dir / name), timeout=5000)
            report['artifacts']['screenshot'] = name
            status['screenshotPath'] = 'runs/' + status['runId'] + '/' + name
        except Exception as error:
            report['screenshotError'] = str(error)
    report['page'] = snapshot
    report['resources'] = resource_snapshot(page.context.browser if page is not None else None)
    report['assessment'] = classify(snapshot, report['duringRun']['events'], report['duringRun']['totals'])
    try:
        # History includes asynchronous failures occurring after browse exited.
        # It is explicitly separate from evidence observed during this run.
        history = json.loads(Path(history_path).read_text())
        report['browserHistory'] = history
    except (OSError, ValueError):
        report['browserHistory'] = None
    status.update(finalUrl=snapshot.get('url', safe_url(page.url) if page else None),
                  pageTitle=snapshot.get('title'), assessment=report['assessment'],
                  resources=report['resources'],
                  diagnosticsPath='runs/' + status['runId'] + '/diagnostics.json')
    write_json(run_dir / 'diagnostics.json', report)
    return report
