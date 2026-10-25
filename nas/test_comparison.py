import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import browser_control
from comparison import listing_visible


class ComparisonTests(unittest.TestCase):
    def test_summary_count_or_error_html_never_counts_as_a_listing(self):
        for evidence in ({}, {'count': 122}, {'count': 0, 'visibleCards': 3},
                         {'count': None, 'visibleArticleLinks': 2}):
            self.assertFalse(listing_visible(evidence))
        self.assertTrue(listing_visible({'count': 122, 'visibleCards': 3}))
        self.assertTrue(listing_visible({'count': 122, 'visibleArticleLinks': 3}))

    def test_display_owner_crash_or_invalid_file_does_not_pause_desktop_forever(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'owner'
            with patch.object(browser_control, 'REQUEST', path):
                for value in ('', 'garbled', '-1', '0'):
                    path.write_text(value)
                    self.assertFalse(browser_control.comparison_active())
                path.write_text(str(os.getpid()))
                self.assertTrue(browser_control.comparison_active())
                with patch.object(browser_control.os, 'kill', side_effect=ProcessLookupError):
                    self.assertFalse(browser_control.comparison_active())
