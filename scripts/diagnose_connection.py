"""공개 원문에 한 번 요청해 DNS·TCP·TLS·HTTP 시간을 확인합니다.

매물 수집·저장·알림은 실행하지 않으며, 응답 본문·쿠키·인증값은 기록하지 않습니다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "http_status": "%{http_code}",
    "redirect_count": "%{num_redirects}",
    "dns_seconds": "%{time_namelookup}",
    "tcp_seconds": "%{time_connect}",
    "tls_seconds": "%{time_appconnect}",
    "first_byte_seconds": "%{time_starttransfer}",
    "total_seconds": "%{time_total}",
}


def classify(report):
    code, http = report["curl_exit"], report.get("http_status", 0)
    if code == 0 and 200 <= http < 300:
        return "http_response_received", "HTTP 응답 수신 성공. 전체 매물 수집 성공 여부는 별도 확인이 필요합니다."
    if http in (401, 403, 429):
        return "http_access_response", f"HTTP {http} 응답 수신. 자동 재시도 없이 진단을 마칩니다."
    if code == 6:
        return "dns_lookup", "호스트 이름 조회에 실패했습니다."
    if code == 7:
        return "tcp_connection", "서버 연결을 맺지 못했습니다."
    if code in (35, 51, 60):
        return "tls_connection", "보안 연결 또는 인증서 확인에 실패했습니다."
    if code == 28:
        # 이 시간값은 시작부터 누적된 값입니다. 리다이렉트가 있으면 특정 구간을 단정하지 않습니다.
        if report.get("redirect_count", 0):
            return "redirect_timeout", "리다이렉트 과정에서 제한 시간을 초과했습니다."
        if not report.get("tcp_seconds"):
            return "connection_timeout", "서버 연결 완료 전 제한 시간을 초과했습니다."
        if not report.get("tls_seconds"):
            return "tls_timeout", "서버 연결 후 보안 연결 완료 전 제한 시간을 초과했습니다."
        if not report.get("first_byte_seconds"):
            return "first_response_timeout", "보안 연결 후 첫 HTTP 응답을 기다리다 제한 시간을 초과했습니다."
        return "body_timeout", "HTTP 응답 후 본문 전송 중 제한 시간을 초과했습니다."
    return "http_or_network_error", "HTTP 또는 네트워크 오류가 발생했습니다. 차단 여부는 이 결과만으로 확정할 수 없습니다."


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    url = config["sourceUrl"]
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "fin.land.naver.com" or parsed.username or parsed.password or parsed.port:
        raise ValueError("진단 대상은 설정된 네이버 공개 HTTPS 원문이어야 합니다.")
    fmt = json.dumps(FIELDS)
    # 일반 curl 한 번만 사용합니다. 인증서 검증·네트워크 경로·브라우저 설정은 바꾸지 않습니다.
    command = ["curl", "--disable", "--silent", "--show-error", "--location", "--max-redirs", "3",
               "--proto", "=https", "--proto-redir", "=https", "--connect-timeout", "12",
               "--max-time", "25", "--output", os.devnull, "--write-out", fmt, url]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=32, check=False)
        raw_report = json.loads(result.stdout)
        report = {key: int(value) if key in ("http_status", "redirect_count") else float(value)
                  for key, value in raw_report.items()}
        report["curl_exit"] = result.returncode
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        report = {"curl_exit": -1, "diagnostic_error": type(exc).__name__}
    stage, message = classify(report)
    report.update(stage=stage, message=message)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## 네이버 연결 진단\n\n" + message + "\n\n```json\n")
            handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n```\n")
            handle.write("\n공개 원문 한 번 요청. 자료·알림 변경 없음. 시간 초과만으로 차단을 확정하지 않습니다.\n")
    return 0 if stage == "http_response_received" else 1


if __name__ == "__main__":
    raise SystemExit(main())
