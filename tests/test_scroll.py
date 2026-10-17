"""Regression: a flat count before the loading sentinel is not end-of-list."""
import sys
import types
import unittest
from unittest.mock import patch

from crawler import collect_browser
from monitor import ValidationError


def listing_text(count, total=118):
    row = "수성범어더블유 103동\n매매 5억 4,000\n오피스텔168OB㎡ (전용78.36OB)20/58층남서향\n확인매물 2026.10.17\n"
    return f"매물 {total}개\n" + row * count


class Page:
    url = "https://fin.land.naver.com/complexes/140635"

    def __init__(self, frames):
        self.frames = frames
        self.reads = 0
        self.advances = 0

    def goto(self, *args, **kwargs):
        return types.SimpleNamespace(status=200)

    def wait_for_timeout(self, *args):
        pass

    def evaluate(self, script, advance):
        if advance:
            self.advances += 1
            return None
        count, total, bottom = self.frames[min(self.reads, len(self.frames) - 1)]
        self.reads += 1
        return {"text": listing_text(count, total), "cardCount": count,
                "atBottom": bottom, "sourceReady": True}


def runtime(page):
    context = types.SimpleNamespace(new_page=lambda: page, close=lambda: None)
    browser = types.SimpleNamespace(new_context=lambda **kw: context, close=lambda: None)
    chromium = types.SimpleNamespace(launch=lambda **kw: browser)

    class Manager:
        def __enter__(self):
            return types.SimpleNamespace(chromium=chromium)

        def __exit__(self, *args):
            pass

    return types.SimpleNamespace(sync_playwright=Manager, TimeoutError=TimeoutError)


class ScrollTests(unittest.TestCase):
    config = {"sourceUrl": Page.url, "allowedDongs": ["101동", "102동", "103동", "105동"]}

    def collect(self, page):
        with patch.dict(sys.modules, {"playwright.sync_api": runtime(page)}):
            return collect_browser(self.config)

    def test_unchanged_count_before_bottom_does_not_stop(self):
        page = Page([(30, 118, False)] * 12 + [(60, 118, False),
                    (90, 118, False), (118, 118, True), (118, 118, True)])
        snapshot = self.collect(page)
        self.assertEqual(len(snapshot["items"]), 118)
        self.assertGreater(page.advances, 10)

    def test_incomplete_list_at_bottom_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "확인 30건"):
            self.collect(Page([(30, 118, True)]))

    def test_total_changed_during_scroll_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "총수가 변경"):
            self.collect(Page([(30, 118, False), (60, 119, False)]))


if __name__ == "__main__":
    unittest.main()
