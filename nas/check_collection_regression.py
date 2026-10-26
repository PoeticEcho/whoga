"""Offline Chromium regression: probe -> full preflight -> all 122 cards.

Run: python nas/check_collection_regression.py [--chromium /usr/bin/chromium]
The fixture models suspected tab-layout variants; it is not captured Naver HTML.
"""
import argparse
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from run import collector, sequence
from diagnostics import page_snapshot

TARGET = 'https://fin.land.naver.com/complexes/140635'
HTML = Path(__file__).with_name('fixtures').joinpath('collection-regression.html').read_text()
BROWSER_PATH = None


class CollectionRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True, **({'executable_path': BROWSER_PATH} if BROWSER_PATH else {}))
        print('Chromium:', cls.browser.version, flush=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.documents = []
        def route(request):
            self.documents.append(request.request.url)
            request.fulfill(status=200, content_type='text/html; charset=utf-8', body=HTML)
        self.context.route('**/*', route)
        self.page.goto('https://fin.land.naver.com/map?layer=fixture')
        self.delays = patch.object(collector.time, 'sleep', side_effect=lambda seconds: self.page.wait_for_timeout(min(seconds * 1000, 20)))
        self.delays.start()

    def tearDown(self):
        self.delays.stop()
        self.context.close()

    def test_probe_then_full_after_original_tab_is_hidden(self):
        raw, expected, _, _, target = collector.collect(self.page, TARGET, probe=True)
        groups, articles = collector.normalize(raw, len(raw), target['complexName'], target['estateTypeText'])
        self.assertEqual((len(groups), len(articles), expected), (3, 33, 122))
        self.page.wait_for_function("document.querySelector('nav').getAttribute('aria-hidden') === 'true'")
        old_tab = self.page.locator('#complex_detail').get_by_role('tab', name=re.compile(r'^매물(?:\s*현재 위치)?$'))
        with self.assertRaises(PlaywrightTimeoutError):
            old_tab.get_attribute('href', timeout=300)
        stages = []
        phases = []
        def stage(mode):
            raw, count, observations, _, target = collector.collect(
                self.page, TARGET, probe=mode == 'probe', progress=lambda name, details: phases.append((mode, name)))
            groups, articles = collector.normalize(raw, len(raw) if mode == 'probe' else count,
                                                   target['complexName'], target['estateTypeText'])
            stages.append((mode, len(groups), len(articles)))
            if mode == 'full':
                self.assertEqual(count, 122)
                self.assertEqual(len({a['articleNo'] for a in articles}), 152)
                self.assertGreater(len(observations), 1)
                self.assertEqual(observations[-1], 122)
                self.assertIn(('full', 'scroll-list'), phases)
        sequence('full', stage)
        self.assertEqual(stages, [('probe', 3, 33), ('full', 122, 152)])
        self.assertEqual(len(self.documents), 1, 'Loaded map session was reset')
        snapshot = page_snapshot(self.page)
        self.assertEqual(snapshot['cardCount'], 122)
        self.assertTrue(snapshot['panelTabs'][0]['ariaHidden'])
        self.assertGreater(snapshot['panelScroll']['top'], 0)

    def test_name_variation_and_duplicate_sticky_tab_keep_identity(self):
        self.page.evaluate("""() => {
          const tab=document.querySelector('nav a');
          tab.textContent='매물\\u200b현재 위치 122';
          const copy=tab.cloneNode(true);copy.setAttribute('aria-hidden','true');tab.after(copy);
        }""")
        self.assertEqual(collector.listing_complex_id(self.page), '140635')
        self.page.locator('nav').evaluate('''el => el.innerHTML = '<a role="tab" href="/complexes/140635">매물<span>현재 위치</span></a>' ''')
        self.assertEqual(collector.listing_complex_id(self.page), '140635')

    def test_identity_rejects_missing_foreign_and_conflicting_links(self):
        for href in ('/complexes/1406350?tab=article', 'https://example.com/complexes/140635?tab=article', '/articles/140635'):
            with self.subTest(href=href):
                self.page.locator('nav a').evaluate('(el, href) => el.setAttribute("href",href)', href)
                try:
                    identity = collector.listing_complex_id(self.page)
                except ValueError:
                    identity = None
                self.assertNotEqual(identity, '140635')
        self.page.locator('nav').evaluate('''el => el.innerHTML = '<a role="tab" href="/complexes/140635?tab=article">매물</a><a role="tab" href="/complexes/999?tab=article">매물</a>' ''')
        with self.assertRaises(ValueError):
            collector.listing_complex_id(self.page)

    def test_collect_rejects_wrong_complex_in_current_document(self):
        self.page.goto(TARGET)
        self.page.locator('nav a').evaluate('el => el.href="/complexes/999?tab=article"')
        with self.assertRaisesRegex(ValueError, 'URL과 다릅니다'):
            collector.collect(self.page, TARGET, probe=True)

    def test_partial_cards_and_partial_groups_still_fail_validation(self):
        raw, count, _, _, target = collector.collect(self.page, TARGET, probe=True)
        with self.assertRaisesRegex(ValueError, '카드 불완전'):
            collector.normalize(raw, count, target['complexName'], target['estateTypeText'])
        raw[0]['articles'].pop()
        with self.assertRaisesRegex(ValueError, '묶음 수량'):
            collector.normalize(raw, len(raw), target['complexName'], target['estateTypeText'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium')
    options, rest = parser.parse_known_args()
    BROWSER_PATH = options.chromium
    unittest.main(argv=[__file__] + rest)
