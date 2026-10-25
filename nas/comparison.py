"""Bounded, sequential headed-browser comparison. Observations are not collections."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit

from browser_control import reserve_display
from browser_runtime import bootstrap, configure, launch
from diagnostics import BrowserEvents, classify, clean, page_snapshot, write_json
from resources import resource_snapshot

PROFILES = [('desktop', 1440, 900), ('responsive', 400, 848), ('android', 400, 848)]
LISTING = r'''(() => {
  const visible = el => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const heading = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]')]
    .filter(visible).map(el => el.textContent.trim()).find(t => /^매물\s*[\d,]+/.test(t));
  const links = [...document.querySelectorAll('a[href]')].filter(el => visible(el) &&
    /^\/articles\/\d+/.test(new URL(el.href, location.href).pathname));
  const cards = [...document.querySelectorAll('ul[class*="ComplexArticleTab"][class*="__article"] > li')].filter(visible);
  return {heading: heading || null, count: heading ? Number(heading.match(/^매물\s*([\d,]+)/)[1].replace(/,/g,'')) : null,
    visibleCards: cards.length, visibleArticleLinks: new Set(links.map(el => new URL(el.href).pathname)).size,
    sampleText: (cards.length ? cards : links).slice(0,3).map(el => el.innerText.slice(0,1200))};
})()'''


def listing_visible(evidence):
    return bool(evidence.get('count', 0) and
                (evidence.get('visibleCards', 0) or evidence.get('visibleArticleLinks', 0)))



def observe(page, seconds):
    deadline = time.monotonic() + seconds
    snapshot, evidence = {}, {}
    last_error = None
    while True:
        try:
            snapshot = page_snapshot(page)
            session = page.context.new_cdp_session(page)
            try:
                evidence = session.send('Runtime.evaluate', dict(expression=LISTING,
                    returnByValue=True, timeout=2000))['result']['value']
            finally:
                session.detach()
            state = classify(snapshot, [])['pageState']
            if listing_visible(evidence) or state == 'access-or-verification-screen':
                break
        except Exception as error:
            last_error = clean(str(error))
        if time.monotonic() >= deadline:
            break
        page.wait_for_timeout(500)
    return snapshot, evidence, last_error


def compare(pw, url, run_dir, status, step, *, seconds=45, launchers=('playwright', 'native'),
            profiles=PROFILES, fixture=None, executable=None):
    run_dir = Path(run_dir)
    target = url + '?tab=article&articleTradeTypes=A1'
    report = dict(runId=status['runId'], mode='compare', build=status['build'], target=target,
                  publicationEligible=False, conditions=[], limitations=[
                      'ChatGPT cloud browser internals and egress IP are not available for replication.',
                      'Android is emulated on Linux Chromium; a narrow viewport does not guarantee lower memory.',
                      'Cards visible is not complete, validated collection. Fresh profile per condition; warm reload within it.'])

    def save():
        status['comparison'] = [dict(condition=c['condition'], outcome=c.get('outcome', 'running'),
            attempts=[dict(action=a['action'], cardsVisible=a['cardsVisible'],
                           pageState=a['assessment']['pageState'],
                           resourceError=a['assessment']['resourceFailureDuringRun']) for a in c['attempts']])
            for c in report['conditions']]
        status['diagnosticsPath'] = 'runs/' + status['runId'] + '/diagnostics.json'
        write_json(run_dir / 'diagnostics.json', report)
        write_json(run_dir / 'status.json', status)

    with reserve_display():
        for launcher in launchers:
            for profile, width, height in profiles:
                name = launcher + '-' + profile
                condition = dict(condition=name, launcher=launcher, profile=profile, attempts=[])
                report['conditions'].append(condition)
                step('compare:' + name)
                save()
                try:
                    with tempfile.TemporaryDirectory(prefix='whoga-compare-') as temporary:
                        with launch(pw, launcher, Path(temporary), executable) as (browser, context):
                            page = context.pages[0] if context.pages else context.new_page()
                            for extra in context.pages[1:]:
                                extra.close()
                            # Client Hints are unavailable on about:blank. Read the native
                            # brands on a trusted local origin before applying emulation.
                            bootstrap(page)
                            configure(page, profile, width, height, browser.version)
                            if fixture:
                                fixture(context, page)
                            events = BrowserEvents(context)
                            condition.update(browserVersion=browser.version, before=resource_snapshot(browser))
                            status['browserVersion'] = browser.version
                            page.bring_to_front()
                            for action in ('initial', 'reload'):
                                step('compare:' + name + ':' + action)
                                start, before_totals = time.time(), dict(events.totals)
                                attempt = dict(action=action)
                                try:
                                    # An error-page URL must never become the reload target.
                                    current = urlsplit(page.url)
                                    expected = urlsplit(url)
                                    if action == 'reload' and current.hostname == expected.hostname and (
                                            current.path == expected.path or current.path == '/map'):
                                        response = page.reload(wait_until='commit', timeout=30000)
                                        attempt['navigation'] = 'reload'
                                    else:
                                        response = page.goto(target, wait_until='commit', timeout=30000)
                                        attempt['navigation'] = 'original-target'
                                    attempt['documentStatus'] = response.status if response else None
                                except Exception as error:
                                    attempt['navigationError'] = clean(str(error))
                                snapshot, evidence, inspection_error = observe(page, seconds)
                                totals = {k: v - before_totals.get(k, 0) for k, v in events.totals.items()}
                                during = [e for e in events.events if e['at'] >= start]
                                assessment = classify(snapshot, during, totals)
                                attempt.update(elapsedSeconds=round(time.time() - start, 2), page=snapshot,
                                    listing=evidence, cardsVisible=listing_visible(evidence), assessment=assessment,
                                    resources=resource_snapshot(browser), duringRun=dict(events=during, totals=totals))
                                if inspection_error:
                                    attempt['inspectionError'] = inspection_error
                                image = name + '-' + action + '.png'
                                try:
                                    page.screenshot(path=str(run_dir / image), timeout=5000)
                                    attempt['screenshot'] = image
                                    status['screenshotPath'] = 'runs/' + status['runId'] + '/' + image
                                except Exception as error:
                                    attempt['screenshotError'] = clean(str(error))
                                condition['attempts'].append(attempt)
                                save()
                                print(json.dumps(clean(dict(condition=name, action=action,
                                      cardsVisible=attempt['cardsVisible'], assessment=assessment,
                                      documentStatus=attempt.get('documentStatus'),
                                      finalUrl=snapshot.get('url'), environment=snapshot.get('environment'),
                                      listing=evidence, resources=attempt['resources'],
                                      network=[e for e in during if e['kind'] in ('http-response', 'request-failed',
                                          'browser-blocked', 'csp-violation')])), ensure_ascii=False), flush=True)
                                if assessment['pageState'] == 'access-or-verification-screen':
                                    condition['outcome'] = 'verification-required'
                                    report['stoppedReason'] = 'verification-required'
                                    save()
                                    return report
                            condition['outcome'] = ('cards-visible' if any(a['cardsVisible'] for a in condition['attempts'])
                                                    else 'no-listing-evidence')
                except Exception as error:
                    condition.update(outcome='failed', error=clean(str(error)))
                save()
    report['completedAt'] = datetime.now(timezone.utc).isoformat()
    save()
    return report
