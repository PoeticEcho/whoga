# 지도 수집 구현 및 검증 기록 — 2026-10-19

## 결론

**정식 운영 인수 미통과.** 코드·회귀 검증은 통과했으나 GitHub Actions의 첫 네이버 문서 응답이 실패해 실수집과 신규 JSON Pages 배포를 완료하지 못했다. 화면 총수를 118로 고정하거나 이전 데이터를 오늘 데이터로 복제하지 않았다.

- 저장소: [PoeticEcho/whoga](https://github.com/PoeticEcho/whoga)
- 작업 브랜치: map-collector-v2, [draft PR #2](https://github.com/PoeticEcho/whoga/pull/2)
- 보호 기준 main: `df653f3f301408fd487e73066e277c97adc4bd36`
- 초기 구현: `72c9c84a378a261389b84e9a248a852873c91cc5`
- 부분 증거/별도 macOS 진단: `5ad90b89853802a53b37b81248514fe4b0e7319f`
- 후속 식별 수정 및 이 기록의 정확한 커밋은 PR의 Commits 참조.
- 기본 URL: [target-url.txt](whoga-naver-collector/target-url.txt), SHA256 `8cb404d7ca5b5bbc0173ca69fb8afc6c0e5289029098da246d52e4dc93b544c8`
- main의 기존 10월 19일 09:25:15 관측 자료 117건을 이번 작업으로 변경하지 않았다.

## 후속 실제 클라우드 관측 — 19:06–19:07 KST

[validation.json](whoga-naver-collector/evidence/cloud-20261019.validation.json)에 기록했다.

| 항목 | 실제 결과 |
|---|---|
| 관측 시각 | 2026-10-19 19:06:00.450–19:07:31.969 KST |
| run_id | 20261019T100600Z-cloud-5f9c9c5be6 |
| 실제 뷰포트 | 1363×936 (Actions의 1440×900과 다름) |
| 로딩 | 30 → 60 → 90 → 120 |
| 완료 근거 | 두 차례 목록 내용 일치, 각 종단 안정 관측 2회 |
| 화면 / 고유 / 중복 / 누락 | 120 / 120 / 0 / 0 |
| 식별 | 단일 실제 ID 47, 묶음/임시 키 73 |
| 동별 카드 | 101동 19 / 102동 52 / 103동 26 / 105동 23 |
| status / completeness | pass / verified (보조 UI 관측 검증 범위) |
| publication | not-attempted, publication_eligible=false |

이는 실제 브라우저 DOM 관측을 수정된 Accumulator·build_snapshot으로 재검증한 결과다. GitHub-hosted Playwright의 자동 navigation/scroll 성공으로 표시하지 않는다. 13시대 식별 집계와 다른 값은 관측 시점별 결과로 보존한다.

기존 앱 JS 검증·120행 목록 생성·동별 합계가 통과했다. 임시 복제본으로 기존 사이트 전체를 빌드하고 로컬 HTTP 서버에서 최신/일일/과거 JSON 및 앱 파일을 확인했다. 기존 한글 경로 `2026-10-17_118건.json`에서 UnicodeEncodeError를 발견해 URL 인코딩을 수정했으며, 재시험에서 전체 경로 HTTP 200/JSON 일치를 확인했다. history/*.json도 검사 대상에 추가했다. 운영 data 파일의 시험 전후 SHA256은 동일했다.

새 파일 `replay_observations.py`, `test_replay.py`, `test_verify_pages.py`와 발행 차단을 추가했다. 보조 관측 자료는 정기 환경을 주더라도 운영 latest로 승격할 수 없다. 원시 카드/관측 전체는 공개 저장소에 추가하지 않았다. GitHub에는 집계·진도·해시·검증 결과만 보존한다.

인수 기준 업데이트: T03의 보조 UI 두 차례 확인과 T12의 실제 자료 JS 처리, T10의 로컬 이력 HTTP 검증은 통과. **Actions T01/T03, 공개 Pages T11은 여전히 미검증/실패 상태**이므로 정식 운영 인수 판단은 유지한다.

## 실제 Actions 실행

아래 값은 다운로드한 실제 validation.json에 근거한다. 모든 시각은 KST.

| 환경 / 로그 | 시작–종료 | 결과 |
|---|---|---|
| [Ubuntu → Browserbase Singapore](https://github.com/PoeticEcho/whoga/actions/runs/39200536804) | 10-19 13:39:21–13:39:54 | navigation / net::ERR_CONNECTION_CLOSED |
| [macOS 기본 Chromium](https://github.com/PoeticEcho/whoga/actions/runs/39200701072) | 10-19 13:41:33–13:42:19 | navigation / TimeoutError(45초 제한) |
| [기존 검사 전용 실행](https://github.com/PoeticEcho/whoga/actions/runs/39200701055) | 실행 페이지 참조 | 검사 성공; live collect 생략 |

| validation 필드 | Singapore | macOS |
|---|---|---|
| run_id | 20261019T043921Z-f2f2aef7c9 | 20261019T044133Z-d8a86a49f8 |
| status / completeness | fail / unknown | fail / unknown |
| 화면 총수 | null — 미확인 | null — 미확인 |
| 수집 고유 건수 | 0 | 0 |
| 중복 / 누락 | null / null — 미확인 | null / null — 미확인 |
| publication | not-attempted | not-attempted |
| 요청 뷰포트 | 1440×900 | 1440×900 |
| Chromium | 155.0.8059.85 | 156.0.8078.4 |

Playwright 1.64.0. macOS 실행은 Python 3.12.10 arm64. Singapore 세션 생성 HTTP 201, 해제 HTTP 200. 브라우저 세션 생성 성공은 대상 접속 성공을 의미하지 않는다. 정확한 차단 주체나 원인은 확정하지 못했다.

증거: [Singapore validation](whoga-naver-collector/evidence/singapore-20261019.validation.json), [macOS validation](whoga-naver-collector/evidence/macos-20261019.validation.json). 접속 실패로 원시 카드/스크롤 진도는 없다. 이 파일은 진단 기록이며 운영용 evidence/validation.json이 아니다.

이전 KR 프록시 실험은 현재 요금제에 포함되지 않아 HTTP 402였다. 이번 수집기는 프록시를 사용하지 않는다. 추가 유료 서비스 구매나 제한 회피는 수행하지 않았다.

## 별도 클라우드 브라우저 관찰과 수정 근거

10월 19일 13시대, 정확한 지도 URL에서 매물 탭의 30 → 60 → 90 → 120개 로딩을 관찰했다. 이는 당시 화면 관찰이며 현재 건수나 Actions 수집 성공을 의미하지 않는다. 필터는 매매/전체면적/전체동으로 확인했다.

문구가 같아도 실제 번호 2655162583, 2655091482가 다른 단일 카드 두 개가 있었다. 텍스트 해시만 사용하면 120개가 119개로 합쳐질 수 있었다. 단일 카드 실제 ID 우선으로 수정한 DOM 집계는 고유 120개(단일 ID 48개, 묶음/임시 키 72개)였다. 이 관찰을 회귀 테스트로 고정했다. 묶음 대표 번호를 묶음 전체의 안정 ID라고 주장하지 않는다. 자동 두 번 완주 수집기와 Pages는 이 관찰로 대체 검증하지 않았다.

## 인수 기준 T01–T14

| ID | 결과와 한계 |
|---|---|
| T01 URL 접속 | 클라우드 브라우저 확인. Actions 접속 실패 — 운영 미통과. |
| T02 지도 조건 | URL 보존/allowlist 테스트 통과. 클라우드 필터 확인. Actions 요청 뷰포트 1440×900, 실제 지도 범위 미검증. |
| T03 긴 스크롤 | 클라우드 120개 확인. 자동 수집기의 라이브 2회 완주 미검증. |
| T04 가상화 | 합성 배치 누적/반복 관측 테스트 통과. |
| T05 중복 식별 | 실제 서로 다른 단일 ID 사례 반영, 묶음 대표 ID 오승격 방지 및 충돌 실패 테스트 통과. |
| T06 빈 목록/제한 | 합성 테스트 통과. 실제 navigation 실패도 fail/unknown으로 종료. |
| T07 실패 시 보존 | 실제 두 Actions에서 publish 미실행, 실패 bundle의 latest 보존 테스트 통과. |
| T08 UTC/KST | KST 스냅샷 날짜/시각 검증 테스트 통과. |
| T09 수동 실행 | 기본 URL을 전달한 수동 실행도 publish 거부 및 원본 보존 테스트 통과. |
| T10 과거 JSON | 발행 준비/과거 자료/동일 날짜 archive 보존 테스트 통과. 신규 공개 경로 HTTP 검증 미실행. |
| T11 Pages | 실수집 실패로 신규 배포/HTTP 200/run_id 검증 미실행 — 인수 미통과. |
| T12 기존 앱 | 기존 Python 24개·JS 22개 회귀 통과. 신규 live 데이터 연결은 미검증. |
| T13 재실행/경합 | 최신 시각 역행/동일 실행 재발행 거부 테스트 통과. 공통 concurrency 설정, 실제 동시 실행 시험 미실행. |
| T14 안전성 | 소스 필드 allowlist, 에러 상세 제한, 세션 기록 비활성화. 복구한 두 validation에 키·쿠키·연락처 없음. 모든 미래 실패의 무누출을 보장하는 평가는 아님. |

최신 로컬 검사 총 **63개 통과**(기존 46 + 수집기/관측/HTTP 검증 17). 합성 테스트 로그의 숫자는 실제 수집량이 아니다. 후속 Actions 검사는 PR Checks에서 커밋별로 확인한다.

## 실제 변경 파일

- `.github/workflows/map_collector.yml`: 검사/수집/발행 분리, 수동 발행 금지, 09:00 KST 일정과 운영 변수, 직접 Pages 배포 및 공개 재검증.
- `.github/workflows/map_native_probe.yml`: macOS 접속 비교 진단, 발행 없음.
- `whoga-naver-collector/collector.py`, `panel.js`: 정확한 지도, 필터·패널 스크롤·즉시 누적·2회 완주, 실패/부분 증거, 단일 ID 우선.
- `build_snapshot.py`: 현재 실행의 검증/해시/시각/식별/총수 확인 및 기존 schemaVersion 2 변환.
- `publish.py`: 정기 기본 URL만 승격, 신선도/역행 방지, 기존 이력·동일 날짜 archive 보존.
- `verify_pages.py`: 최신·지도 이력·기존 data 이력 JSON 내용과 기존 앱 HTTP 확인.
- `test_collector.py`: 13개 오류·경계·회귀 테스트.
- `requirements.txt`, `target-url.txt`: 버전 및 원문 URL 고정.
- `scripts/build_site.py`: 기존 사이트 전체를 유지하고 허용된 지도 JSON만 추가.
- `.gitignore`: 실행 산출물/임시 발행 폴더 제외.
- 루트/수집기 README, instruction.md 실행 부록, 본 기록, 실제 실패 validation 2개.

## 배포·재현·다음 단계

신규 latest.json·snapshot-YYYY-MM-DD.json은 **생성/배포하지 않았다**. 따라서 신규 공개 주소의 HTTP 200 결과도 없다. 기존 앱의 Pages를 새 데이터 전용 사이트로 교체하지 않았다.

재현 명령은 [수집기 README](whoga-naver-collector/README.md)에 있다. 현재 PR은 병합하지 않았고 정기 운영도 활성화하지 않았다. main은 위 보호 기준을 유지한다.

다음 차단점은 같은 CLI가 일반 네트워크에서 실제 문서를 읽는지 확인하는 것이다. NAS DS420+는 아직 연결하지 않았다. 접근 가능한 NAS/PC에서 우선 수집 전용 실행 → 두 번 완주 및 결과 검증 → Pages 배포/HTTP 재조회 순으로 확인해야 한다. 환경 확보 없이 Actions 접속 성공이나 매일 자동화 성공을 보장할 수 없다. 정상 검증 전 ENABLE_MAP_DAILY를 켜지 않는다.

롤백이 필요한 main 변경은 없으며, PR을 병합하지 않으면 기존 구현과 데이터를 유지한다.
