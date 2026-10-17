"""같은 공개 주소에서 HTTP/1.1과 curl-cffi Chrome 프로필을 한 번씩 비교합니다.

연결 호환성 시험이며, 스냅샷·알림·인증 정보를 저장하거나 변경하지 않습니다.
"""
from __future__ import annotations

from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from monitor import now_kst, parse_raw_text, validate_snapshot
from scripts.diagnose_connection import FIELDS, classify


class PageText(HTMLParser):
    """스크립트·스타일·문서 메타데이터를 매물 원문으로 취급하지 않습니다."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("head", "script", "style", "noscript", "svg"):
            self.hidden.append(tag)

    def handle_endtag(self, tag):
        if self.hidden and self.hidden[-1] == tag:
            self.hidden.pop()

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def inspect_body(body, config):
    parser = PageText()
    parser.feed(body)
    text = "\n".join(parser.parts)
    limited = any(marker in text for marker in
                  ("비정상적인 접근", "접근이 제한", "서비스 이용이 제한", "자동입력 방지", "로봇이 아닙니다"))
    expected, items = parse_raw_text(text, config["allowedDongs"])
    complete = False
    if not limited:
        try:
            validate_snapshot({"date": now_kst()[:10], "declaredCount": expected, "items": items},
                              require_complete=True, allowed_dongs=config["allowedDongs"])
            complete = True
        except ValueError:
            pass
    return {"access_notice": limited, "declared_items": expected,
            "parsed_items": len(items), "complete_items": complete}


def probe_http1(url, config):
    with tempfile.TemporaryDirectory() as directory:
        body_file = Path(directory) / "body.html"
        command = ["curl", "--disable", "--http1.1", "--silent", "--show-error", "--location",
                   "--max-redirs", "3", "--proto", "=https", "--proto-redir", "=https",
                   "--connect-timeout", "12", "--max-time", "25", "--max-filesize", "5000000",
                   "--user-agent", "whoga/1.0 (+https://poeticecho.github.io/whoga/; connection-test)",
                   "--header", "Accept-Language: ko-KR,ko;q=0.9", "--output", str(body_file),
                   "--write-out", json.dumps(FIELDS), url]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=32, check=False)
            metrics = json.loads(result.stdout)
            report = {key: int(value) if key in ("http_status", "redirect_count") else float(value)
                      for key, value in metrics.items()}
            report["curl_exit"] = result.returncode
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            report = {"curl_exit": -1, "error_type": type(exc).__name__}
        report["stage"], report["message"] = classify(report)
        body = body_file.read_text(encoding="utf-8", errors="replace") if body_file.exists() else ""
        report.update(inspect_body(body, config))
        report.update(client="system_curl_http1", body_bytes=body_file.stat().st_size if body_file.exists() else 0)
        return report


def probe_cffi(url, config):
    from curl_cffi import __version__, requests
    started = time.monotonic()
    report = {"client": "curl_cffi_chrome", "library_version": __version__}
    try:
        response = requests.get(url, impersonate="chrome", timeout=25, max_redirects=3, verify=True,
                                headers={"Accept-Language": "ko-KR,ko;q=0.9"})
        report.update(http_status=response.status_code, total_seconds=round(time.monotonic()-started, 4),
                      body_bytes=len(response.content), http_version=str(response.http_version))
        report.update(inspect_body(response.text, config))
        report["stage"] = "http_response_received"
    except Exception as exc:
        # 네트워크 예외 본문에는 URL이 포함될 수 있어 유형·코드만 기록합니다.
        report.update(http_status=0, total_seconds=round(time.monotonic()-started, 4),
                      error_type=type(exc).__name__, curl_exit=getattr(exc, "code", None),
                      stage="request_failed", complete_items=False)
    return report


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    url = config["sourceUrl"]
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "fin.land.naver.com" or parsed.username or parsed.password or parsed.port:
        raise ValueError("설정된 네이버 공개 HTTPS 원문만 시험합니다.")
    reports = [probe_http1(url, config)]
    first = reports[0]
    # 명시적 제한 응답을 다른 통신 방식으로 재시도하지 않습니다.
    if first.get("http_status") not in (401, 403, 429) and not first.get("access_notice"):
        reports.append(probe_cffi(url, config))
    output = {"scope": "connection-comparison-only", "checked_at": now_kst(), "reports": reports,
              "snapshots_written": False, "notifications_sent": False}
    serialized = json.dumps(output, ensure_ascii=False, indent=2)
    print(serialized)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## 네이버 통신 호환성 비교\n\n")
            handle.write("HTTP 응답과 전체 매물 수집 여부를 따로 확인합니다. 기존 자료·알림 변경 없음.\n\n```json\n")
            handle.write(serialized + "\n```\n")
    return 0 if any(r.get("complete_items") for r in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
