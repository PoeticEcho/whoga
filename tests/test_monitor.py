import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import crawler
import monitor as m
from scripts import notify
from scripts import build_site

FIXTURES = Path(__file__).parent / "fixtures"


def item(price=6.0, article_id=None, floor="20/58층", high=None):
    return {"id": "item_1", "articleId": article_id, "dong": "101동", "type": "84OA",
            "floor": floor, "floorCat": "중층", "direction": "북서향",
            "minPrice": price, "maxPrice": high if high is not None else price,
            "agencyCount": 1, "confirmDate": "2026.10.17"}


def snapshot(items=None, date="2026-10-17", declared=None):
    items = [item()] if items is None else items
    return {"date": date, "declaredCount": len(items) if declared is None else declared, "count": len(items), "items": items}


class ValidationTests(unittest.TestCase):
    def test_price_formats(self):
        for raw, expected in [("5억 8,000", 5.8), ("6억", 6), ("5.8억", 5.8), ("58,000", 5.8), ("5000만", .5), ("6억 5,123만원", 6.5123)]:
            self.assertEqual(m.price_eok(raw), expected)
        for raw in ("가격 협의", "", "-1", "0", "5억~6억"):
            with self.assertRaises(m.ValidationError):
                m.price_eok(raw)

    def test_declared_count_does_not_read_price_as_count(self):
        self.assertIsNone(m.declared_count("매매 5억 8,000"))
        self.assertEqual(m.declared_count("매매 120\n전세 30"), 120)

    def test_copied_text_range_and_types(self):
        declared, rows = m.parse_raw_text((FIXTURES / "naver_copied.txt").read_text())
        self.assertEqual((declared, len(rows)), (2, 2))
        self.assertEqual((rows[0]["type"], rows[0]["minPrice"]), ("78OB", 5.8))
        self.assertEqual((rows[1]["type"], rows[1]["minPrice"], rows[1]["maxPrice"]), ("84OA", 6, 6.2))

    def test_invalid_numbers_duplicate_ids_and_unknown_types(self):
        cases = [snapshot([item(float("nan"))]), snapshot([item(float("inf"))]), snapshot([item(-1)]), snapshot([item(high=5)]), snapshot([item(article_id="a"), item(article_id="a")])]
        unknown = item(); unknown["type"] = "임의타입"; cases.append(snapshot([unknown]))
        for case in cases:
            with self.assertRaises(m.ValidationError): m.validate_snapshot(case)

    def test_partial_and_zero_are_not_saved_as_live_success(self):
        for case in [snapshot(declared=2), snapshot([])]:
            with self.assertRaises(m.ValidationError): m.validate_snapshot(case, require_complete=True)


class DiffTests(unittest.TestCase):
    def test_same_article_price_is_confirmed(self):
        result = m.compare_snapshots(snapshot([item(5.8, "123")]), snapshot([item(6, "123")]))
        self.assertEqual(len(result["changed"]), 1)
        self.assertEqual(result["candidates"], [])

    def test_different_article_ids_not_merged(self):
        result = m.compare_snapshots(snapshot([item(5.8, "456")]), snapshot([item(6, "123")]))
        self.assertEqual((len(result["added"]), len(result["unobserved"])), (1, 1))
        self.assertFalse(result["changed"] or result["candidates"])

    def test_legacy_price_is_candidate(self):
        result = m.compare_snapshots(snapshot([item(5.8)]), snapshot([item(6)]))
        self.assertEqual(len(result["candidates"]), 1)
        self.assertFalse(result["changed"])

    def test_ambiguous_same_location_not_force_matched(self):
        result = m.compare_snapshots(snapshot([item(5.8), item(5.9)]), snapshot([item(6), item(6.1)]))
        self.assertFalse(result["candidates"])
        self.assertEqual((len(result["added"]), len(result["unobserved"])), (2, 2))

    def test_maximum_price_alone_is_change(self):
        result = m.compare_snapshots(snapshot([item(6, "a", high=6.3)]), snapshot([item(6, "a", high=6.2)]))
        self.assertEqual(len(result["changed"]), 1)

    def test_partial_data_does_not_create_mass_removals(self):
        result = m.compare_snapshots(snapshot(declared=120), snapshot([item(), item()]))
        self.assertFalse(result["available"])
        self.assertEqual(result["unobserved"], [])

    def test_legacy_exact_multiset_preserves_counts(self):
        result = m.compare_snapshots(snapshot([item(), item()]), snapshot([item()]))
        self.assertEqual((len(result["unchanged"]), len(result["added"])), (1, 1))


class PersistenceTests(unittest.TestCase):
    def test_failure_preserves_last_success_and_snapshot_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            m.save_snapshot(tmp, snapshot(), source_kind="manual")
            path = Path(tmp) / "2026-10-17.json"; before = path.read_bytes()
            last = m.read_json(Path(tmp) / "status.json")["lastSuccessAt"]
            m.record_failure(tmp, "접근 제한")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(m.read_json(Path(tmp) / "status.json")["lastSuccessAt"], last)
            self.assertEqual(m.read_json(Path(tmp) / "status.json")["lastAttemptResult"], "failed")
            with self.assertRaises(m.ValidationError): m.save_snapshot(tmp, snapshot(declared=2))
            self.assertEqual(path.read_bytes(), before)

    def test_canonical_date_is_latest_and_previous_skips_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, obj in [("2026-10-17", snapshot()), ("2026-10-17_118건", snapshot(date="2026-10-17 (118건)")), ("2026-10-16", snapshot(date="2026-10-16")), ("2026-08-06", snapshot(date="2026-08-06", declared=108))]:
                m.atomic_json(Path(tmp) / f"{name}.json", obj)
            idx = m.rebuild_index(tmp)
            self.assertEqual(idx["latest"], "2026-10-17")
            self.assertEqual(m.previous_snapshot(tmp, snapshot())["date"], "2026-10-16")

    def test_cli_dry_run_and_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.json"; m.atomic_json(source, snapshot())
            dest = Path(tmp) / "data"
            args = ["--input", str(source), "--data-dir", str(dest)]
            self.assertEqual(crawler.main(args + ["--dry-run"]), 0)
            self.assertFalse(dest.exists())
            self.assertEqual(crawler.main(args), 0)
            self.assertEqual(crawler.main(args), 1)

    def test_fingerprint_ignores_fetch_time_and_row_order(self):
        a = snapshot([item(6, "a"), item(5.8, "b")]); b = copy.deepcopy(a)
        b["items"].reverse(); b["collectedAt"] = "다른 시간"
        self.assertEqual(m.fingerprint(a), m.fingerprint(b))
        b["items"][0]["maxPrice"] += .1
        self.assertNotEqual(m.fingerprint(a), m.fingerprint(b))


class NotificationTests(unittest.TestCase):
    def test_utf16_chunking(self):
        text = "범어W🏠" * 2000
        chunks = notify.split_message(text)
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(c.encode("utf-16-le")) // 2 <= 3500 for c in chunks))

    def test_failed_send_does_not_leak_token(self):
        def denied(*args, **kwargs): raise OSError("https://api.telegram.org/botSECRET/sendMessage")
        with self.assertRaises(RuntimeError) as caught:
            notify.send_telegram("test", "SECRET", "123", opener=denied)
        self.assertNotIn("SECRET", str(caught.exception))

    def test_same_notification_not_resent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "data").mkdir()
            m.save_snapshot(root / "data", snapshot(), source_kind="manual")
            m.atomic_json(root / "config.json", {})
            with patch.object(notify, "ROOT", root), patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "test-chat"}), patch.object(notify, "send_telegram") as send:
                self.assertEqual(notify.main(["--enabled"]), 0)
                self.assertEqual(notify.main(["--enabled"]), 0)
                self.assertEqual(send.call_count, 1)


class AdapterTests(unittest.TestCase):
    def test_structured_payload_keeps_ids_and_filters_other_estates(self):
        config = m.read_json(m.ROOT / "config.json")
        row = {"articleNo": "123456", "tradeTypeCode": "A1", "buildingName": "101동", "areaName": "180OA", "floorInfo": "20/58", "direction": "북서향", "dealOrWarrantPrc": "6억"}
        wrong = {**row, "articleNo": "222", "realEstateTypeCode": "APT"}
        _, rows = crawler.structured_items({"articleList": [row, wrong], "totalCount": 2}, config)
        self.assertEqual([r["articleId"] for r in rows], ["123456"])


class BuildTests(unittest.TestCase):
    def test_only_public_files_and_public_configuration_are_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "source"; root.mkdir()
            (root / "data").mkdir(); (root / "assets").mkdir()
            (root / "index.html").write_text('<html lang="ko"></html>')
            (root / ".nojekyll").touch()
            (root / "crawler.py").write_text("PRIVATE_IMPLEMENTATION")
            (root / ".env").write_text("SECRET")
            (root / "_state").mkdir(); (root / "_state/notifications.json").write_text("PRIVATE_STATE")
            m.atomic_json(root / "config.json", {"complexId": "140635", "telegram_bot_token": "SECRET"})
            m.atomic_json(root / "data/2026-10-17.json", snapshot())
            m.atomic_json(root / "data/status.json", {"lastAttemptResult": "not_run"})
            with patch.object(build_site, "ROOT", root): destination = build_site.build(Path(tmp) / "out")
            self.assertFalse((destination / "crawler.py").exists())
            self.assertFalse((destination / ".env").exists())
            self.assertFalse((destination / "_state").exists())
            self.assertNotIn("SECRET", (destination / "config.json").read_text())


if __name__ == "__main__":
    unittest.main()
