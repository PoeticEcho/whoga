# WhoGa 지도 수집기

2026-10-19 상태: 구현·단위/회귀 검증 완료, **Actions 실수집 및 Pages 신규 경로 배포 미완료**. [검증 기록](../VERIFICATION_MAP.md), [PR #2](https://github.com/PoeticEcho/whoga/pull/2), [원본 지침 및 실행 부록](../instruction.md)을 함께 읽는다.

## 수집 계약

- `target-url.txt`의 지도 URL을 원문 그대로 사용한다. center/layer를 재인코딩하지 않는다. HTTPS Naver /map, 필수 파라미터, A1/A02만 허용한다.
- 브라우저는 1440×900을 요청한다. 실제 뷰포트·매매/전체면적/전체동 필터·화면 총수를 증거에 기록한다. 이 뷰포트의 Actions 실화면 검증은 접속 실패로 아직 못 했다.
- 매물 패널을 높이의 85%씩 이동하며 즉시 누적한다. 총수는 UI에서 읽으며 118이나 120으로 고정하지 않는다.
- 총수 일치, 패널 끝, 로딩 종료, 두 번의 안정 관측을 요구한다. 목록 전체를 두 번 훑어 내용이 일치해야 통과한다.
- 단일 카드는 실제 article ID를 우선한다. 묶음의 대표 중개 매물번호는 묶음 ID로 승격하지 않는다. 나머지는 허용 필드 텍스트의 실행 내 SHA256 키를 쓴다. 같은 관측에 구분 불가능한 카드가 있으면 실패한다.
- 묶음 키는 장기간 동일 매물임을 보장하지 않는다. 묶음 개수와 개별 중개 매물 수를 혼동하지 않으며, 매물 부재를 거래 완료로 판단하지 않는다.
- 동/가격/면적·층·향/확인일/중개사 수만 원시 카드에 보존한다. 연락처·중개사명·설명·쿠키·접속 토큰은 보존하지 않는다.
- 빈 목록, 부분 수집, 필터/총수 변경, 파싱 오류, 접근 제한은 발행하지 않는다. 스크롤 제한은 240초, 첫 문서 응답은 45초다.

## 실행과 증거

저장소 루트에서 실행한다. 아래 명령은 로컬 Chromium 수집이며 발행하지 않는다.

```sh
python -m pip install -r whoga-naver-collector/requirements.txt
python -m playwright install chromium
python whoga-naver-collector/collector.py --transport local
python whoga-naver-collector/build_snapshot.py collector-runs/<실제-run_id>
```

Linux에서 시스템 의존성이 없으면 `python -m playwright install --with-deps chromium`을 사용한다. Playwright와 requests는 requirements에 고정되어 있다.

Browserbase 시험은 `BROWSERBASE_API_KEY`를 환경 시크릿으로 주입한 뒤 `--transport browserbase --region ap-southeast-1`로 실행한다. 일반 세션 한 개만 생성하며 프록시, CAPTCHA 풀이, advanced stealth를 사용하지 않는다. API 키를 코드·명령 인수·로그에 넣지 않는다. 현재 이 경로는 세션 생성에는 성공하지만 네이버 연결이 종료된다.

수동 URL은 `MANUAL_URL` 환경변수로 한 번만 전달한다. 원본 파일은 바뀌지 않는다. 허용 필터와 기존 단지/유형 파서는 그대로이므로 임의 지도의 범용 수집기는 아니다.

각 `collector-runs/<run_id>/`에는 validation.json이 남는다. DOM을 읽었다면 raw-cards.json 부분 체크포인트도 남는다. 통과 시 원시 카드 해시, dictionaries.json, snapshot.json, compact-snapshot.txt를 생성한다. 빌더는 **명시한 실행 폴더**의 상태·run_id·URL·해시·시각·종단 증거를 재검증한다. 접속 실패는 정상 0건이 아니다.

## Actions와 발행

`.github/workflows/map_collector.yml`:
1. 기존 Python/JS 및 새 수집기 테스트가 통과해야 수집 가능.
2. 작업 브랜치 일반 push는 검사만 한다. 커밋 메시지의 `[live-map-trial]` 또는 workflow_dispatch는 시험 수집이며 발행하지 않는다.
3. 정기는 UTC 00:00(한국 09:00) 목표다. main에 병합하고 저장소 변수 `ENABLE_MAP_DAILY=true`인 경우만 실행한다. **실수집·배포 검증 전 활성화하지 않는다.**
4. 기본 URL의 main 정기 실행만 최신 데이터 승격 가능. 30분 넘은 자료, 미래 시각, 기존 최신보다 이르거나 같은 시각은 거부한다.
5. 기존 WhoGa schemaVersion 2/items 구조를 유지하며 data/YYYY-MM-DD.json 및 지도 최신/일일 JSON을 준비한다. 같은 날의 기존 data는 history에 보존한다.
6. 기존 HTML/CSS/JS·과거 data를 포함해 전체 사이트를 빌드하고 같은 workflow에서 Pages artifact를 직접 배포한다.
7. 공개 최신/일일/기존 이력 JSON과 앱 파일의 HTTP 상태 및 JSON 내용을 재검증한다. Git 커밋만으로 배포 성공을 선언하지 않는다.

Pages에는 latest.json, snapshot-YYYY-MM-DD.json, history/*.json, evidence/validation.json만 추가된다. raw-cards·dictionaries·브라우저 진단은 Pages에 복사하지 않는다. 실패한 실행의 증거는 7일짜리 Actions artifact에 남는다. 보존한 두 진단 JSON은 이 PR의 evidence 디렉터리에서 확인할 수 있다.

기존 `daily_briefing.yml`은 08:13 KST 일정과 `ENABLE_DAILY` 변수를 사용한다. 운영 전환 시 기존 수집 일정을 비활성화하고 단일 발행 주체를 유지한다. 두 워크플로는 동일 concurrency 그룹을 쓴다. 현재 PR은 draft이며 main과 기존 데이터는 변경하지 않았다.

## 재현 테스트

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s whoga-naver-collector -p 'test_*.py' -v
node --test tests/*.test.mjs
```

2026-10-19 로컬 결과: 24 + 13 + 22 = 59개 통과. 합성 테스트는 네이버 실수집 성공 증거가 아니다.

## 다음 검증

현재 남은 첫 단계는 일반 브라우저로 네이버에 접속 가능한 실행 환경에서 동일 CLI가 전체 목록 두 번을 읽는지 확인하는 것이다. NAS DS420+는 접속·설치·실행하지 않았다. NAS를 사용할 경우 우선 수집 전용으로 위 명령을 검증하며 자동 발행은 활성화하지 않는다. 이후에만 runner 구성과 정기 운영을 결정한다.

네이버 화면에 체계적 복제·재배포 제한 안내가 관찰되었다. 정기 수집과 공개 데이터 운영 범위는 해당 서비스의 허용 범위를 확인한 뒤 결정해야 한다. 이 문서는 이용 허가나 법률 판단을 대신하지 않는다.
