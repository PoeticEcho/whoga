"""공개 매물 페이지를 일반 브라우저로 관측합니다. 차단을 우회하지 않습니다."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from monitor import (ROOT, KST, ValidationError, declared_count, floor_category,
                     now_kst, parse_raw_text, price_eok, read_json, record_failure,
                     save_snapshot, validate_snapshot)


def structured_items(payload, config):
    """알려진 네이버 매물 JSON 형태만 처리합니다. 알 수 없는 필드는 실패로 남깁니다."""
    found = {}
    totals = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("articleList"), list):
                for key in ("totalCount", "totalArticleCount"):
                    n = node.get(key)
                    if isinstance(n, int) and not isinstance(n, bool):
                        totals.append(n)
            if node.get("articleNo") and node.get("tradeTypeCode") == "A1":
                try:
                    item = adapt_article(node, config)
                    if item:
                        found[item["articleId"]] = item
                except (ValidationError, ValueError, TypeError):
                    pass
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(payload)
    # API의 total은 동일 오피스텔 매물의 총계라고 입증할 수 없어 참고값으로만 사용합니다.
    return totals, list(found.values())


def adapt_article(row, config):
    if row.get("complexNo") and str(row["complexNo"]) != config["complexId"]:
        return None
    building = str(row.get("buildingName", ""))
    building = building if building.endswith("동") else building + "동"
    if building not in config["allowedDongs"]:
        return None
    estate_type = row.get("realEstateTypeCode")
    if estate_type and estate_type not in ("OPST", "OBYG"):
        return None
    area_name = str(row.get("areaName", "")).upper()
    area2 = float(row.get("area2") or 0)
    if "168OB" in area_name.replace(" ", "") or abs(area2 - 78.36) < 0.06:
        area = "78OB"
    elif "180OA" in area_name.replace(" ", "") or abs(area2 - 84.02) < 0.06:
        area = "84OA"
    else:
        return None
    floor = str(row.get("floorInfo", "")).replace("층", "")
    if not re.fullmatch(r"[\d저중고]+/\d+", floor):
        return None
    direction = row.get("direction") or ""
    if not re.fullmatch(r"(?:남서|남동|북서|북동|서|동|남|북)향", direction):
        return None
    raw = str(row.get("dealOrWarrantPrc") or "")
    parts = raw.split("~")
    return {"articleId": str(row["articleNo"]), "id": str(row["articleNo"]),
            "dong": building, "type": area, "floor": floor + "층",
            "floorCat": floor_category(floor), "direction": direction,
            "priceRaw": raw, "minPrice": price_eok(parts[0]), "maxPrice": price_eok(parts[-1]),
            "agencyInfo": str(row.get("realtorName") or ""), "agencyCount": 1,
            "confirmDate": str(row.get("articleConfirmYmd") or ""),
            "desc": str(row.get("articleFeatureDesc") or ""), "baseTag": ""}


def collect_browser(config, max_scrolls=45):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ValidationError("수집용 Playwright가 없습니다. 설치 안내를 확인해 주세요.") from exc
    captured = {}
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 1000}, locale="ko-KR")
        page = context.new_page()

        def observe(response):
            if "/article" not in response.url.lower() or "json" not in response.headers.get("content-type", ""):
                return
            # 페이지가 정상적으로 읽은 JSON 응답만 관측합니다. 인증 헤더·쿠키를 저장하지 않습니다.
            try:
                _, rows = structured_items(response.json(), config)
                for item in rows:
                    captured[item["articleId"]] = item
            except Exception:
                pass

        page.on("response", observe)
        try:
            response = page.goto(config["sourceUrl"], wait_until="domcontentloaded", timeout=45000)
            if response and response.status in (401, 403, 429):
                raise ValidationError(f"네이버 접근 제한(HTTP {response.status}). 수집을 중단했습니다.")
            stable_rounds, previous_count = 0, -1
            expected, best_items = None, []
            for _ in range(max_scrolls):
                page.wait_for_timeout(1100)
                raw = page.locator("body").inner_text(timeout=12000)
                if any(x in raw for x in ("비정상적인 접근", "접근이 제한", "서비스 이용이 제한", "자동입력 방지", "로봇이 아닙니다")):
                    raise ValidationError("네이버 접근 제한 화면이 표시되어 수집을 중단했습니다.")
                expected, text_items = parse_raw_text(raw, config["allowedDongs"])
                if expected is not None:
                    choices = [list(captured.values()), text_items]
                    for items in choices:
                        if expected > 0 and len(items) == expected:
                            snapshot = {"date": now_kst()[:10], "declaredCount": expected, "items": items}
                            validate_snapshot(snapshot, require_complete=True, allowed_dongs=config["allowedDongs"])
                            return snapshot
                best_items = max([best_items, text_items, list(captured.values())], key=len)
                stable_rounds = stable_rounds + 1 if len(best_items) == previous_count else 0
                previous_count = len(best_items)
                if stable_rounds >= 10:
                    break
                page.evaluate("""() => {
                  const scrollables = [...document.querySelectorAll('main,section,div')]
                    .filter(e => e.scrollHeight > e.clientHeight + 80 && e.clientHeight > 200
                      && ['auto','scroll'].includes(getComputedStyle(e).overflowY));
                  for (const e of scrollables) e.scrollTop += Math.max(500, e.clientHeight * .85);
                  window.scrollBy(0, 850);
                }""")
            raise ValidationError(f"수집 형식을 확인하지 못했습니다. 원문 총수 {expected if expected is not None else '미확인'} / 확인 {len(best_items)}건. 기존 자료를 유지합니다.")
        finally:
            context.close()
            browser.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="범어W 일일 스냅샷 수집·원문 가져오기")
    parser.add_argument("--input", type=Path, help="수동 JSON 또는 네이버 복사 원문(.txt)")
    parser.add_argument("--date", help="수동 입력 기준일 YYYY-MM-DD")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--replace", action="store_true", help="수동 입력으로 같은 날짜를 교체")
    parser.add_argument("--dry-run", action="store_true", help="검사 결과만 표시. 파일·알림 변경 없음")
    args = parser.parse_args(argv)
    config = read_json(ROOT / "config.json")
    try:
        if args.input:
            raw = args.input.read_text(encoding="utf-8-sig")
            if args.input.suffix.lower() == ".json":
                snapshot = json.loads(raw)
                if args.date:
                    snapshot["date"] = args.date
            else:
                if not args.date:
                    raise ValidationError("복사 원문은 --date YYYY-MM-DD를 지정해 주세요.")
                expected, items = parse_raw_text(raw, config["allowedDongs"])
                snapshot = {"date": args.date, "declaredCount": expected, "items": items}
            kind = "manual"
            validate_snapshot(snapshot, require_complete=True, allowed_dongs=config["allowedDongs"])
            target = args.data_dir / (snapshot["date"][:10] + ".json")
            if target.exists() and not args.replace and not args.dry_run:
                raise ValidationError("같은 날짜 파일이 있습니다. 교체하려면 --replace를 지정해 주세요.")
        else:
            if args.date:
                raise ValidationError("--date는 수동 입력에서만 사용할 수 있습니다.")
            snapshot = collect_browser(config)
            kind = "naver-live"
        validation = validate_snapshot(snapshot, require_complete=True, allowed_dongs=config["allowedDongs"])
        if not args.dry_run:
            save_snapshot(args.data_dir, snapshot, source_kind=kind)
        print(f"{'검사' if args.dry_run else '저장'} 완료: {snapshot['date'][:10]} · {validation['parsedCount']}건")
        return 0
    except Exception as exc:
        # 네트워크 오류에는 URL·세션 정보가 들어갈 수 있어 공개 상태 파일에 원문 예외를 저장하지 않습니다.
        message = str(exc) if isinstance(exc, ValidationError) else "수집 연결 또는 페이지 형식 확인에 실패했습니다. Actions 로그와 수동 입력 안내를 확인해 주세요."
        if not args.dry_run and not args.input:
            record_failure(args.data_dir, message)
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
