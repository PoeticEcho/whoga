# Actions 수집 경로 및 첨부 v2 검토
검토일: 2026-10-20 KST. 작업 브랜치 map-collector-v2, [PR #2](https://github.com/PoeticEcho/whoga/pull/2).

## 결론
현재까지 성공한 것은 별도 클라우드 브라우저의 실제 UI 관측과 데이터 검증이다. GitHub-hosted 러너의 실수집 성공은 확보하지 못했다. 코드 테스트 성공과 수집 성공을 분리한다. 여러 브라우저가 문서 응답 전에 실패하므로 묶음 펼침·스크롤 파서를 바꾸는 것만으로 현재 접속 문제를 해결했다고 볼 수 없다. 정확한 차단 주체/정책은 미확인이다.

## 첨부본 확인
검토한 파일: README (2).md, whoga-naver-collector-v2 (1).zip. 별도 README와 ZIP 내부 README는 바이트 단위로 일치한다.
- 원본 패키지 테스트 10개 통과. 첨부 데이터의 118카드/537등록, 마포 16카드/125등록 정합성 검사 통과. 당시 관측 자료이며 현재 건수나 이번 Actions 성공 증거가 아니다.
- 기본 target-url.txt는 기존 지도 URL과 정확히 일치한다.
- 원본 collector.py SHA256: e99d8f5434674ecbf410bcb3262bc3fe09e9fcd3e7fd0555ddfc3a0a40842b54.
- 일반화된 단지명·유형·층 처리, 매매 필터 확인, 중개사 묶음 펼침/접힘, 개별 등록 ID 검증은 유용하다.
- `/articles/2651166087/out-link-bridge?cpId=asil`의 ID 추출을 기존 panel.js에 반영하고 Node 회귀 검사를 추가했다.
- cards/articles와 기존 WhoGa items는 호환되지 않는다. 537등록을 기존 앱의 537개 매물 카드로 표시하면 단위가 달라진다. 개별 중개 등록 ID는 고유 호실 수가 아니다.
- 원본은 전체 카드가 DOM에 남는다는 가정으로 끝까지 로드한 뒤 nth(index)로 처리한다. 가상화 누적·두 차례 동일 내용 확인은 기존 수집기의 별도 장점이다.
- 원본의 원자적 파일 교체와 잠금은 유용하지만 여러 파일의 발행 전체를 원자적으로 만드는 것은 아니다. 현재 실행의 run_id/해시 검증, 수동 발행 격리, 기존 이력/Pages 통합은 기존 파이프라인을 유지해야 한다.
- 원본 워크플로는 저장소 루트 배치와 artifact 보존용이다. 기존 저장소 루트에 덮어쓰지 않았다. 실험용 소스만 experiments/supplied-v2에 분리했다.
- checkout/setup-python/upload-artifact의 v7 태그는 GitHub API로 실제 존재를 확인했다. 버전 오기로 판단하지 않았다.
- 원본 일정 예시는 09:17이며 비활성화 상태다. 기존 지침의 09:00 목표를 변경하지 않았다.

## 실제 실행 결과
| 경로 | 결과 | 증거 |
|---|---|---|
| 기존 Ubuntu Chromium | 첫 문서 응답 실패 | 이전 VERIFICATION_MAP.md |
| macOS Chromium | navigation 45초 TimeoutError | [39200701072](https://github.com/PoeticEcho/whoga/actions/runs/39200701072) |
| Windows Edge 최초 | tzdata 누락으로 테스트 단계 실패, 접속은 미실행 | [39237081953](https://github.com/PoeticEcho/whoga/actions/runs/39237081953) |
| Windows Edge 수정 후 | 00:19:16–00:20:05 KST, navigation TimeoutError | [39276870486](https://github.com/PoeticEcho/whoga/actions/runs/39276870486) |
| 첨부 v2 Ubuntu headless Chromium | 00:19:15–00:20:03 KST, Page.goto ERR_CONNECTION_RESET | [39276870655](https://github.com/PoeticEcho/whoga/actions/runs/39276870655) |
| 첨부 v2 Ubuntu headed Chromium/Xvfb | 00:20:29–00:21:21 KST, 같은 ERR_CONNECTION_RESET | 같은 실행의 headed job |
| Ubuntu Firefox | 00:22:03–00:22:49 KST, navigation TimeoutError | [39277168834](https://github.com/PoeticEcho/whoga/actions/runs/39277168834) |
| Ubuntu WebKit | 00:23:42–00:24:30 KST, navigation TimeoutError | 같은 실행의 webkit job |
| Actions → Browserbase Singapore | 세션 생성201/해제200, 문서 ERR_CONNECTION_CLOSED | [39200536804](https://github.com/PoeticEcho/whoga/actions/runs/39200536804) |
| 이전 Browserbase KR 프록시 옵션 | 요금제 미지원402, 성공 경로 아님 | 이전 기록 |
| 이전 Firecrawl | 초기 목록/스크롤 이후 오류, 전체 수집 미확인 | 이전 기록 |

Windows 수정: `tzdata==2025.2; sys_platform == "win32"` 의존성을 추가하고 설치를 테스트 앞으로 이동했다. 수정 후 수집기 테스트 17개는 통과했다. IANA 시간대 자료가 없는 Windows에서 tzdata 의존성을 권고하는 Python 공식 문서와 일치한다.

Windows 네트워크 점검은 DNS 해석, TCP 접속, TLSv1.3 협상까지 0.99초에 성공했다. 이후 Edge 154.0.4258.62의 문서 응답이 실패했다. 따라서 DNS 전체 장애나 브라우저 미설치로 설명되지 않는다. 이 결과만으로 IP 차단·봇 판정·HTTP 프로토콜 문제 중 하나를 확정하지 않는다.

수집기에 도달한 위 실패 실행은 화면 총수 미확인, 수집 고유0, 중복/누락 미확인이다. 정상 0건이 아니며 latest 승격·Pages 배포는 하지 않았다. 첨부본은 표본 probe 단계에서 실패해 full 단계가 생략됐다.

실제 artifact에서 복구한 상태 JSON은 whoga-naver-collector/evidence 아래 날짜별 파일로 보존했다. 원시 매물 전체·쿠키·인증 토큰은 추가하지 않았다.

## 가능한 실행 방식과 남은 조건
“모든 방법”은 무한한 옵션 조합을 성공할 때까지 반복한다는 의미로 해석하지 않았다. 서로 다른 실행 방식의 확인 범위를 아래처럼 구분한다.

| 방식 | 현재 판단 | 다음 실행에 필요한 것 |
|---|---|---|
| GitHub-hosted의 OS/브라우저 변경 | Ubuntu/macOS/Windows, Chromium/Edge/Firefox/WebKit 비교 | 확인된 실패를 근거 없이 반복하지 않음 |
| headed/Xvfb | 첨부본으로 실제 시험, 실패 | headed만으로 해결된다는 근거 없음 |
| Playwright 버전 변경 | 1.63.0 첨부본과 1.64.0 기존 코드 모두 시험 | 무작위 버전 변경 대신 특정 회귀 증거 필요 |
| Docker | 설치/버전 재현에 도움. 별도 네트워크가 생기는 방법은 아님 | 브라우저 이미지·패키지 일치; 접속 해결 효과는 미검증 |
| Actions → 일반 원격 브라우저 | Browserbase 현재 연결로 시험 실패 | 접속 가능한 승인된 원격 서비스와 계정/접속 정보 |
| Actions 자체 실행기(PC/NAS/전용 VM) | GitHub가 일정·로그·검증을 관리하고 사용자 환경이 브라우저 실행. 유력한 다음 검증 경로이나 성공 보장 없음 | 같은 URL/CLI가 정상 동작하는 환경 확보, 격리된 runner 등록 |
| 국내 전용 VM의 자체 실행기 | 구조적으로 같은 자체 실행기 방식, 미시험 | 사용자가 보유/승인한 VM. 유료 자원을 임의 구매하지 않음 |
| 기존 Work 클라우드 브라우저 | UI 관측 성공. Actions 호출용 연결 정보는 현재 확보하지 못함 | 수동/보조 수집 성공을 무인 Actions 성공으로 표시하지 않음 |
| 공급자가 허용한 API/데이터 제공 | 계약·허용된 제공 경로를 확보하면 별도 설계 가능 | 현재 연결된 데이터 제공 경로 없음. 비공식 API 추측/토큰 복사 방식은 채택하지 않음 |
| 프록시 회전/stealth/CAPTCHA 우회 | 원본 지침에서 제외 | 구현하지 않음 |

자체 실행기도 GitHub Actions다. 다만 공개 whoga 저장소에 개인 자료가 있는 NAS를 그대로 연결하는 구성은 피하고, 전용 격리 실행 환경에서 신뢰한 코드만 실행하도록 설계해야 한다. GitHub 공식 문서도 공개 저장소의 자체 실행기 위험을 경고한다. 이번에는 runner를 등록하거나 시스템 접근 권한을 변경하지 않았다.

## 다음 인수 순서
1. 접속 가능한 승인된 실행 환경에서 같은 고정 지도와 실제 필터/뷰포트를 확인한다.
2. 전체 목록/묶음 단위를 구분하고 현재 실행만 검증한다. probe 성공만으로 운영하지 않는다.
3. 기존 WhoGa 스키마 변환·이력 보존 후 Pages를 배포하고 공개 JSON의 HTTP200/run_id를 확인한다.
4. 위 단계 통과 후에만 기존 수집 일정과 충돌하지 않도록 09:00 정기를 활성화한다.

main 및 기존 운영 데이터는 변경하지 않았다. 새 실험 workflow는 작업 브랜치의 해당 workflow 파일 변경 또는 수동 실행에만 반응하며 정기 실행을 추가하지 않았다.

## 공식 근거
- https://docs.python.org/3/library/zoneinfo.html
- https://pypi.org/project/tzdata/2025.2/
- https://playwright.dev/python/docs/ci
- https://playwright.dev/python/docs/browsers
- https://docs.github.com/en/actions/concepts/runners/self-hosted-runners
- https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners


## 최종 코드 검사

기존 프로젝트 Python 24개 + 수집기 17개 + JavaScript 23개 = 64개. 첨부본 원본 테스트 10개는 별도 수행했다. 공식 문서/코드 태그 확인 및 실수집 실패 증거를 분리 보존했다.


## 단지 직접 주소 추가 검증 (2026-10-20 KST)

사용자 지정 URL은 `https://fin.land.naver.com/complexes/140635`이며 쿼리/지도 좌표를 붙이지 않는다. 첨부본의 URL 검증 함수는 단지번호 140635를 정상 인식한다. 실제 UI에서 단지번호를 다시 대조하고 매매 필터를 선택한다. 짧은 주소 자체에 거래유형·지도 조건이 포함되지 않으므로 기존 exact-map과 동일 범위라고 간주하지 않는다.

`.github/workflows/complex_probe.yml`은 `runner=github-hosted`를 Ubuntu로 고정하며, 수동 입력 `mode=probe`는 처음 세 카드만 검사한다. `mode=full`은 같은 실행에서 probe를 먼저 성공해야 전체 수집으로 넘어간다. 이번 workflow 추가 push도 사용자 요청대로 probe→성공 시 full 순서로 실행한다. 산출물은 검증용 artifact에만 저장한다.

실제 실행: https://github.com/PoeticEcho/whoga/actions/runs/39278424648

당시 조회 API는 queued를 반환했으나, 06:41 KST 이후 재조회한 완료 로그에서는 아래 실행 이력이 확인됐다. 이전 대기 상태를 최종 결과로 사용하지 않는다.


## 단지 주소 실제 실행 최종 결과 (2026-10-20 06:41 KST 이후 확인)

| GitHub-hosted 환경 | probe 시작–실패 (KST) | 결과 | full |
|---|---|---|---|
| ubuntu-latest | 00:30:23–00:31:12 | Page.goto: net::ERR_CONNECTION_RESET | skipped |
| ubuntu-22.04 | 00:40:07–00:40:56 | Page.goto: net::ERR_CONNECTION_RESET | skipped |

- latest 실행: https://github.com/PoeticEcho/whoga/actions/runs/39278424648
- Ubuntu22 실행: https://github.com/PoeticEcho/whoga/actions/runs/39279671410
- 두 환경 모두 설치와 브라우저 실행 이후 첫 단지 문서 탐색에서 실패했다. 단지번호 대조·매매 필터 선택·카드 수집에는 도달하지 않았다. 따라서 0건 매물로 해석하지 않는다.
- artifact의 원본 probe/status.json을 evidence/complex-140635-*-20261020.status.json에 보존했다. latestPreserved=true, 전체 수집/배포 없음.
- 짧은 주소는 코드가 지원하지만 실제 네트워크 성공은 확인되지 않았다. URL 길이나 지도 쿼리가 유일한 원인이라는 가설은 이번 결과로 뒷받침되지 않는다. 서버/중간망의 연결 종료 원인은 확정하지 않는다.
- 동일 커밋 CI https://github.com/PoeticEcho/whoga/actions/runs/39278424455 에서 Python24+17, JS23=64개 통과를 완료 로그로 확인했다. 이는 무인 실수집 성공과 별개다.
- 다음 실수집 검증에는 정상 접속 가능한 승인된 별도 실행 환경 또는 공급자의 허용된 데이터 제공 경로가 필요하다. 현재 github-hosted 조건에서는 성공 경로 미확보. 조건 변경 없이 성공했다고 보고하지 않는다.


## DS420+ NAS Docker 검증판
`nas/`에 Dockerfile, Compose, probe→full 게이트, 일반 사용자/읽기전용 컨테이너 및 Chromium 샌드박드 설정, 설치 문서를 추가했다. CPU linux/amd64용이며 DS420j에 동일 적용하지 않는다. Playwright 1.63.0 이미지와 Python 패키지 버전을 일치시켰다.

Actions https://github.com/PoeticEcho/whoga/actions/runs/39330724224 에서 게이트 검사 3개, Compose 검사, 실제 Docker 이미지 빌드, 외부 사이트 접속 없는 Chromium 샌드박드 smoke 모두 통과. 최초 smoke의 chroot 차단을 seccomp에서 해당 호출만 허용하여 수정했고 cap_drop=ALL 유지. browser-ready는 네이버 수집 성공을 뜻하지 않는다.

NAS 연결/설치/probe/full은 미수행. 실제 모델과 DSM/메모리 확인 후 NAS에서 smoke→probe→full 순서로 실행해야 한다. GitHub runner 등록, 정기 일정, 운영 데이터 발행은 미활성화. 상세 설치 안내: nas/README.md.
