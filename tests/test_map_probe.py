import unittest
from scripts.probe_map import structural_summary, terminal_page


class MapProbeTests(unittest.TestCase):
    def test_summary_excludes_listing_data_and_tokens(self):
        value = {'totalCount': 26, 'articleList': [{'phone':'private'}], 'token':'private'}
        summary = structural_summary(value)
        self.assertEqual(summary['arrayLengths'], {'articleList': 1})
        self.assertEqual(summary['counts'], {'totalCount': 26})
        self.assertNotIn('private', str(summary))
        self.assertNotIn('token', str(summary))

    def test_page_not_found_is_separate_from_access_restriction(self):
        self.assertEqual(terminal_page('페이지를 찾을 수 없습니다'), 'ordinary-not-found')
        self.assertEqual(terminal_page('비정상적인 접근으로 서비스 이용이 제한됩니다'), 'access-restricted')
        self.assertIsNone(terminal_page('매물0개 로딩중'))
        self.assertIsNone(terminal_page('매물26개 수성범어더블유 103동'))


if __name__ == '__main__':
    unittest.main()
