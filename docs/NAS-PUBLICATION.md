# NAS JSON → 공개 호가앱

NAS의 `full.json`이 `PoeticEcho/whoga`의 `map-collector-v2` 브랜치 `nas-imports/140635/<runId>.json`에 도착하면 `whoga · NAS JSON to public app`이 검증·변환·main 저장·Pages 배포를 수행한다.

## 실행 경로

1. NAS 업로드 커밋이 생기면 해당 브랜치의 workflow가 실행된다. 실행 코드는 항상 최신 `main`에서 가져오고 NAS 브랜치에서는 JSON만 읽는다.
2. 기본 브랜치에 등록된 5분 간격 예약도 누락된 업로드를 확인한다. GitHub 대기열에 따라 실행이 늦어질 수 있다.
3. `scripts/import_nas.py`가 NAS 스키마·전체 모드·단지·매매·건수·묶음 구성·매물번호 중복·가격 숫자와 텍스트·동/타입/층/향을 검사한다. 실패하면 공개 데이터 변경 전에 중단한다.
4. 화면 카드 1개를 앱 매물 행 1개로 변환한다. 카드 122개/개별매물 578개라면 공개 목록은 122행이다. 각 카드의 모든 `articleNos`를 보존하되 다중 매물 묶음에 임의 대표 `articleId`를 만들지 않는다.
5. 한국 시각 관측일 기준 `data/YYYY-MM-DD.json`을 생성하고 기존 날짜 자료를 유지하며 `index.json`, `status.json`을 갱신한다. 수집 시각은 NAS의 `collectedAt`을 보존한다. 동일 runId는 재반영하지 않고 같은 날짜의 더 최신 자료는 오래된 업로드로 덮어쓰지 않는다.
6. 앱 테스트와 정적 빌드 성공 후 data 파일을 한 커밋으로 main에 저장하고 같은 workflow가 Pages artifact를 배포한다. `GITHUB_TOKEN` 커밋이 다른 push workflow를 자동 실행하지 않는 점을 고려한 구성이다.

raw JSON의 `publicationEligible=false`를 그대로 앱에 복사하거나 무시하고 바로 배포하는 방식이 아니다. 새 변환기가 공개 앱에 필요한 범위를 다시 검증해 스키마 v2의 별도 공개 스냅샷을 만든다. 원본 NAS 파일은 그대로 유지한다. 묶음에는 대표 매물번호가 없어 기존 앱에서 조건 기반 비교 대상으로 처리되며, 개별번호 확정 변동과 구분한다.

## 실패와 복구

- NAS의 토큰·자동 업로드 설정이 없으면 이 workflow에 입력이 도착하지 않는다. 이 구현이 NAS 접속이나 토큰 등록을 대신하지 않는다.
- JSON이 없으면 예약 확인은 정상 종료하고 새 관측 자료를 만들지 않는다. 이전 자료를 오늘 수집으로 바꾸지 않는다.
- 잘못된 입력이 있으면 workflow를 실패로 표시하며 공개 자료는 유지한다. 문제 파일을 수정한 다음 다시 실행한다.
- main이 동시에 바뀌어 push가 거절되면 강제 push하지 않는다. 다음 실행에서 최신 main 기준으로 다시 계산한다.
- GitHub 저장 성공과 Pages 배포 성공을 나눠 확인한다. 배포만 실패하면 Actions에서 실패 실행을 재실행하거나 `workflow_dispatch`로 수동 실행한다. 수동 실행은 데이터 변화가 없어도 현재 main의 Pages 재배포를 수행한다.
- 기존 Pages 작업과 같은 concurrency 그룹을 사용해 배포 작업을 직렬화한다.

## 검증 범위

Python 검사 45개, JavaScript 검사 33개 통과. 합성 NAS 자료의 변환·기존 이력 보존·재실행 멱등성·오래된 자료 거부·부분/중복/가격 오류 거부를 검사했다. 실제 NAS JSON이 GitHub에 도착하기 전에는 실제 수집부터 공개 반영까지 성공했다고 판단하지 않는다.
