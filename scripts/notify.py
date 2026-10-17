"""텔레그램 발송 전용. 토큰은 환경변수에서만 읽고 웹 파일에 저장하지 않습니다."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from monitor import ROOT, atomic_json, build_briefing, fingerprint, now_kst, previous_snapshot, read_json


def split_message(text, limit=3500):
    """UTF-16 길이로 제한하여 한글·이모지가 있어도 Telegram 한도를 넘지 않습니다."""
    chunks, current, units = [], [], 0
    for char in text:
        size = len(char.encode("utf-16-le")) // 2
        if units + size > limit:
            chunks.append("".join(current))
            current, units = [], 0
        current.append(char); units += size
    if current:
        chunks.append("".join(current))
    return chunks


def send_telegram(text, token, chat_id, opener=None):
    opener = opener or urllib.request.urlopen
    for part in split_message(text):
        payload = json.dumps({"chat_id": chat_id, "text": part,
                              "link_preview_options": {"is_disabled": True}}).encode()
        request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload,
                                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            with opener(request, timeout=25) as response:
                result = json.loads(response.read())
            if not result.get("ok"):
                raise RuntimeError("텔레그램 API가 발송을 거부했습니다.")
        except Exception:
            # urllib 예외에 토큰 URL이 포함될 수 있어 원문을 출력하지 않습니다.
            raise RuntimeError("텔레그램 발송 결과를 확인하지 못했습니다. 토큰·대화 ID·네트워크를 확인해 주세요. 자동 재전송은 하지 않습니다.") from None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="메시지만 출력. 발송·상태 변경 없음")
    parser.add_argument("--enabled", action="store_true", help="실제 알림 발송")
    parser.add_argument("--collection-failed", action="store_true")
    parser.add_argument("--deployment-failed", action="store_true")
    args = parser.parse_args(argv)
    status = read_json(ROOT / "data/status.json", {})
    if args.collection_failed:
        date = now_kst()[:10]
        text = f"범어W 호가 수집 실패 · {date}\n{status.get('message', '수집 결과를 확인해 주세요.')}\n마지막 정상 자료를 유지했습니다.\n미수집을 변동 없음으로 처리하지 않습니다."
        key = f"failure:{date}"
    else:
        index = read_json(ROOT / "data/index.json")
        entry = next(e for e in index["snapshots"] if e["id"] == index["latest"])
        snapshot = read_json(ROOT / "data" / entry["file"])
        text = build_briefing(snapshot, previous_snapshot(ROOT / "data", snapshot))
        key = "success:" + fingerprint(snapshot)
    config = read_json(ROOT / "config.json")
    run_url = os.getenv("RUN_URL", "")
    site_url = os.getenv("SITE_URL", "") or config.get("siteUrl", "")
    if args.deployment_failed:
        text += "\n웹페이지 배포는 실패했습니다. 저장소의 최신 자료와 실행 기록을 확인해 주세요."
        key += ":deploy-failed"
    elif site_url.startswith("https://"):
        text += "\n대시보드: " + site_url
    if run_url.startswith("https://github.com/"):
        text += "\n실행 기록: " + run_url
    if args.dry_run:
        print(text)
        return 0
    if not args.enabled:
        print("알림 발송을 선택하지 않아 건너뜁니다.")
        return 0
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("알림 발송 실패: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID Secrets를 등록해 주세요.", file=sys.stderr)
        return 1
    # 수신자를 바꾸면 별도 발송으로 취급하되 ID 원문은 저장하지 않습니다.
    key += ":" + hashlib.sha256(chat_id.encode()).hexdigest()[:16]
    state_path = ROOT / "_state/notifications.json"
    state = read_json(state_path, {"sent": []})
    if key in state["sent"]:
        print("이미 발송한 동일 자료입니다. 중복 알림을 생략합니다.")
        return 0
    try:
        send_telegram(text, token, chat_id)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    state["sent"] = (state["sent"] + [key])[-200:]
    state["lastSentAt"] = now_kst()
    atomic_json(state_path, state)
    print("텔레그램 알림을 발송했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
