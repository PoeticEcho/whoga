"""범어W 스냅샷 검증·비교·저장. 외부 의존성 없이 실행합니다."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
KST = ZoneInfo("Asia/Seoul")


class ValidationError(ValueError):
    pass


def now_kst():
    return datetime.now(KST).isoformat(timespec="seconds")


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def price_eok(text):
    """한글 호가 또는 만원 단위 숫자를 억원으로 변환. 불명확한 범위는 호출자가 분리."""
    text = re.sub(r"\s+", "", str(text)).replace(",", "").removesuffix("원")
    if not text or "~" in text or "협의" in text:
        raise ValidationError("호가 숫자를 확인할 수 없습니다.")
    try:
        if "억" in text:
            match = re.fullmatch(r"(\d+(?:\.\d+)?)억(?:(\d+)만?)?", text)
            if not match:
                raise ValidationError("지원하지 않는 호가 형식입니다.")
            value = Decimal(match[1]) + Decimal(match[2] or "0") / 10000
        else:
            value = Decimal(text.removesuffix("만")) / 10000
        if value <= 0:
            raise ValidationError("호가는 0보다 커야 합니다.")
        return round(float(value), 4)
    except InvalidOperation as exc:
        raise ValidationError("호가 형식을 확인해 주세요.") from exc


def floor_category(value):
    first = str(value).split("/")[0]
    if first.isdigit():
        return "저층" if int(first) <= 19 else "중층" if int(first) <= 38 else "고층"
    return next((label for label in ("저층", "중층", "고층") if label[0] in first), "기타")


def declared_count(text):
    patterns = [
        r"(?:전체\s*)?매물\s*([\d,]+)\s*(?:개|건)",
        r"매매\s*([\d,]+)\s*건",
        r"매매\s*([\d,]+)\s*(?=전세|월세|단기임대|전체매물|매물목록)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match[1].replace(",", ""))
    return None


def parse_raw_text(raw, allowed_dongs=None):
    """기존 패키지의 복사 원문 형식. 모르는 타입·층을 추정해 채우지 않습니다."""
    allowed_dongs = set(allowed_dongs or ["101동", "102동", "103동", "105동"])
    items = []
    # 원문/모바일 표시 이름 두 가지를 허용합니다.
    chunks = re.split(r"(?=(?:수성범어더블유|수성범어W)\s*\d+동)", raw)
    for chunk in chunks:
        building = re.match(r"(?:수성범어더블유|수성범어W)\s*(\d+동)", chunk)
        price = re.search(r"매매\s*(\d[\d,]*(?:\.\d+)?\s*억(?:\s*[\d,]+)?(?:\s*~\s*\d[\d,]*(?:\.\d+)?\s*억(?:\s*[\d,]+)?)?)", chunk)
        area = re.search(r"(168\s*OB|180\s*OA|78\.36|84\.02)", chunk, re.I)
        floor = re.search(r"([\d저중고]+)\s*/\s*(\d+)\s*층", chunk)
        direction = re.search(r"(남서향|남동향|북서향|북동향|서향|동향|남향|북향)", chunk)
        if not (building and price and area and floor and direction):
            continue
        if building[1] not in allowed_dongs:
            continue
        parts = price[1].split("~")
        low, high = price_eok(parts[0]), price_eok(parts[-1])
        confirm = re.search(r"(?:확인매물|등록)\s*(\d{4}[.-]\d{2}[.-]\d{2})", chunk)
        agencies = re.search(r"중개사\s*(\d+)곳", chunk)
        desc = re.search(r'[“"]([^”"]+)[”"]', chunk)
        items.append({
            "id": f"text_{len(items)+1}", "articleId": None,
            "dong": building[1],
            "type": "84OA" if re.search(r"180|84\.02", area[1]) else "78OB",
            "floor": f"{floor[1]}/{floor[2]}층", "direction": direction[1],
            "floorCat": floor_category(floor[1]),
            "priceRaw": re.sub(r"\s+", " ", price[1]).strip(),
            "minPrice": low, "maxPrice": high,
            "confirmDate": confirm[1] if confirm else "",
            "agencyCount": int(agencies[1]) if agencies else 1,
            "agencyInfo": f"중개사 {agencies[1]}곳 공동등록" if agencies else "",
            "desc": desc[1] if desc else "", "baseTag": "",
        })
    return declared_count(raw), items


def validate_snapshot(snapshot, require_complete=False, allowed_dongs=None):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("items"), list):
        raise ValidationError("items 배열이 있는 스냅샷이 필요합니다.")
    try:
        datetime.strptime(snapshot.get("date", "")[:10], "%Y-%m-%d")
    except (ValueError, TypeError) as exc:
        raise ValidationError("스냅샷 날짜는 YYYY-MM-DD 형식이어야 합니다.") from exc
    items = snapshot["items"]
    declared = snapshot.get("declaredCount")
    if isinstance(declared, bool) or not isinstance(declared, int) or declared < 0:
        raise ValidationError("원문 총 매물 수가 필요합니다.")
    if "count" in snapshot and snapshot["count"] != len(items):
        raise ValidationError("저장된 count와 실제 items 수가 다릅니다.")
    seen_ids = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError("매물 행은 객체여야 합니다.")
        for field in ("dong", "type", "floor", "direction"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValidationError(f"매물의 {field} 항목이 없습니다.")
        if allowed_dongs and item["dong"] not in allowed_dongs:
            raise ValidationError("대상 동 범위를 벗어난 매물이 있습니다.")
        if item["type"] not in ("78OB", "84OA"):
            raise ValidationError("대상 오피스텔 타입을 확인해 주세요.")
        for key in ("minPrice", "maxPrice"):
            value = item.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValidationError("호가 숫자가 유효하지 않습니다.")
        if item["maxPrice"] < item["minPrice"]:
            raise ValidationError("최대 호가가 최소 호가보다 작습니다.")
        article_id = str(item.get("articleId") or "")
        if article_id:
            if not re.fullmatch(r"[\w-]{1,80}", article_id):
                raise ValidationError("매물번호 형식을 확인해 주세요.")
            if article_id in seen_ids:
                raise ValidationError("중복 매물번호가 있습니다.")
            seen_ids.add(article_id)
    complete = declared == len(items)
    if require_complete and (not complete or not items):
        raise ValidationError(f"수집 보류: 원문 {declared}건 / 확인 {len(items)}건. 기존 데이터를 유지합니다.")
    return {"complete": complete, "declaredCount": declared, "parsedCount": len(items)}


def location_key(item):
    return tuple(str(item.get(k, "")) for k in ("dong", "type", "floor", "direction"))


def price_key(item):
    return (round(item["minPrice"], 4), round(item.get("maxPrice", item["minPrice"]), 4))


def exact_key(item):
    return location_key(item) + price_key(item)


def compare_snapshots(current, previous):
    """번호 없는 행은 조건 관측치로 비교. 동일 호수나 거래 성사로 단정하지 않습니다."""
    result = {"available": False, "reason": "비교 스냅샷이 없습니다.", "unchanged": [],
              "changed": [], "candidates": [], "added": [], "unobserved": []}
    if previous is None:
        return result
    if not validate_snapshot(current)["complete"] or not validate_snapshot(previous)["complete"]:
        result["reason"] = "일부 수집 스냅샷은 신규·미관측 비교에서 제외합니다."
        return result
    result.update(available=True, reason="")
    curr, prev = current["items"], previous["items"]
    used_c, used_p = set(), set()
    by_id = {str(x["articleId"]): j for j, x in enumerate(prev) if x.get("articleId")}
    for i, item in enumerate(curr):
        j = by_id.get(str(item.get("articleId"))) if item.get("articleId") else None
        if j is not None:
            used_c.add(i); used_p.add(j)
            field = "unchanged" if price_key(item) == price_key(prev[j]) else "changed"
            result[field].append({"current": item, "previous": prev[j]})
    # 한쪽에만 번호가 있는 과거 자료는 조건으로 비교합니다. 서로 다른 번호는 연결하지 않습니다.
    for i, item in enumerate(curr):
        if i in used_c:
            continue
        for j, old in enumerate(prev):
            if j in used_p or (item.get("articleId") and old.get("articleId")):
                continue
            if exact_key(item) == exact_key(old):
                used_c.add(i); used_p.add(j)
                result["unchanged"].append({"current": item, "previous": old})
                break
    c_groups, p_groups = defaultdict(list), defaultdict(list)
    for i, item in enumerate(curr):
        if i not in used_c:
            c_groups[location_key(item)].append(i)
    for j, item in enumerate(prev):
        if j not in used_p:
            p_groups[location_key(item)].append(j)
    for key, indices in c_groups.items():
        old_indices = p_groups.get(key, [])
        if len(indices) == len(old_indices) == 1:
            i, j = indices[0], old_indices[0]
            if not (curr[i].get("articleId") and prev[j].get("articleId")) and all(k not in ("", "-") for k in key):
                used_c.add(i); used_p.add(j)
                result["candidates"].append({"current": curr[i], "previous": prev[j]})
    result["added"] = [x for i, x in enumerate(curr) if i not in used_c]
    result["unobserved"] = [x for j, x in enumerate(prev) if j not in used_p]
    return result


def fingerprint(snapshot):
    rows = [{k: row.get(k) for k in ("articleId", "dong", "type", "floor", "direction", "minPrice", "maxPrice", "agencyCount", "confirmDate")} for row in snapshot["items"]]
    rows.sort(key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False))
    raw = json.dumps([snapshot["date"][:10], rows], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def rebuild_index(data_dir):
    entries = []
    for path in sorted(Path(data_dir).glob("*.json")):
        if path.name in ("index.json", "status.json"):
            continue
        snap = read_json(path)
        quality = validate_snapshot(snap)
        entries.append({"id": path.stem, "date": snap["date"][:10],
                        "label": snap.get("label", snap["date"]), "file": path.name,
                        "count": len(snap["items"]), "declaredCount": snap["declaredCount"],
                        "complete": quality["complete"], "sourceKind": snap.get("source", {}).get("kind", "provided"),
                        "collectedAt": snap.get("collectedAt")})
    entries.sort(key=lambda e: (e["date"], e["id"] == e["date"], e["id"]), reverse=True)
    latest = next((e["id"] for e in entries if e["complete"]), entries[0]["id"] if entries else None)
    result = {"schemaVersion": 2, "latest": latest, "snapshots": entries}
    atomic_json(Path(data_dir) / "index.json", result)
    return result


def save_snapshot(data_dir, snapshot, source_kind="naver-live"):
    config = read_json(ROOT / "config.json")
    validation = validate_snapshot(snapshot, require_complete=True, allowed_dongs=config["allowedDongs"])
    date = snapshot["date"][:10]
    snapshot.update(date=date, count=len(snapshot["items"]), schemaVersion=2,
                    collectedAt=now_kst(), source={"kind": source_kind, "url": config["sourceUrl"]},
                    validation={**validation, "method": "declared-count-and-required-fields", "identityCount": sum(bool(i.get("articleId")) for i in snapshot["items"])})
    atomic_json(Path(data_dir) / f"{date}.json", snapshot)
    rebuild_index(data_dir)
    status = read_json(Path(data_dir) / "status.json", {})
    status.update(lastAttemptAt=now_kst(), lastAttemptResult="success", lastSuccessAt=now_kst(),
                  latestCollectedDate=date, sourceKind=source_kind, message="수집 수량과 필수 항목 검사를 통과했습니다.")
    atomic_json(Path(data_dir) / "status.json", status)


def record_failure(data_dir, message):
    status = read_json(Path(data_dir) / "status.json", {})
    status.update(lastAttemptAt=now_kst(), lastAttemptResult="failed", message=message)
    atomic_json(Path(data_dir) / "status.json", status)


def previous_snapshot(data_dir, current):
    index = read_json(Path(data_dir) / "index.json", {})
    for entry in index.get("snapshots", []):
        if entry["date"] < current["date"][:10] and entry["complete"]:
            return read_json(Path(data_dir) / entry["file"])
    return None


def build_briefing(current, previous=None):
    diff = compare_snapshots(current, previous)
    lines = [f"범어W 오피스텔 호가 · {current['date'][:10]}", f"관측 {len(current['items'])}건 / 원문 {current['declaredCount']}건"]
    source = current.get("source", {}).get("kind", "provided")
    lines.append("네이버 자동 수집" if source == "naver-live" else "제공·수동 입력 자료 (실시간 수집 아님)")
    for area in ("78OB", "84OA"):
        prices = [i["minPrice"] for i in current["items"] if i["type"] == area]
        if prices:
            lines.append(f"{area} {len(prices)}건 · 최저 {min(prices):g}억 · 중앙값 {median(prices):g}억")
    if diff["available"]:
        lines += [f"비교일 {previous['date'][:10]}",
                  f"추가 관측 {len(diff['added'])} · 미관측 {len(diff['unobserved'])}",
                  f"번호 확인 호가 변동 {len(diff['changed'])} · 조건 기준 변동 후보 {len(diff['candidates'])}"]
        for pair in diff["changed"][:6]:
            item, old = pair["current"], pair["previous"]
            lines.append(f"{item['dong']} {item['type']} {item['floor']} {old['minPrice']:g} → {item['minPrice']:g}억")
    else:
        lines.append(diff["reason"])
    lines += ["호가는 매도 희망가입니다. 미관측은 거래 완료를 뜻하지 않습니다.",
              "범위 호가의 통계는 최저값 기준입니다."]
    return "\n".join(lines)
