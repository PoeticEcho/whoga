# WhoGa 네이버 부동산 지도 수집기 · Work 실행 지침서

> 파일명: `instruction.md`  
> 프로젝트: `whoga-naver-collector` / WhoGa(호가)  
> 작성 기준일: 2026-10-19 (Asia/Seoul)  
> 문서 리비전: v2.0 — Map URL 고정 기준 / GitHub Actions 우선 / Pages 배포 검증  
> 상태: **실행 지시서** (실제 소스 검토·라이브 수집·배포 성공을 의미하지 않음)

---

## 0. ChatGPT Work에 전달할 최상위 지시

**목표:** 기존 `whoga-naver-collector` 코드를 확인·수정하여, **아래에 지정한 네이버 부동산 지도 URL을 기준으로** GitHub Actions에서 매일 자동 수집하고, 해당 화면에서 로드 가능한 모든 대상 매물의 원시 데이터와 검증 결과를 기록한 다음, **검증을 통과한 최신 데이터만** JSON으로 발행한다. GitHub Pages를 통해 WhoGa 프론트엔드가 최신·과거 스냅샷을 조회할 수 있게 한다.

1. **기존 구현 재사용 우선.** 기존 `README.md`, `requirements.txt`, `target-url.txt`, `collector.py`, `build_snapshot.py`, `test_collector.py`, `evidence/`, JSON 스키마 및 WhoGa 프론트엔드를 먼저 조사한다. 아직 첨부되지 않은 ZIP이나 GitHub 저장소를 확인한 척하지 않는다.
2. **GitHub Actions가 1순위 운영 환경.** Synology NAS DS420+(RAM 6GB)는 백업·문제 재현용 2순위 환경으로 남긴다.
3. **단지 URL이 아닌 지도 URL 기반.** 수집 범위는 임의로 행정구역·단지 목록으로 변경하지 않는다. 실제 수집 범위는 지도 크기·뷰포트·필터·줌 및 네이버 화면의 목록 로딩 동작에 종속된다.
4. **수집 성공과 발행 성공을 분리.** 페이지 접속, 목록 완료, 데이터 검증, Git 저장, Pages 발행, 공개 URL 재조회가 모두 통과해야 완료로 표시한다.
5. **실제 동작 테스트 필수.** 가상의 매물 건수·주소·가격·스크린샷이나 허위 성공 로그를 작성하지 않는다. 접근 제한·CAPTCHA·데이터 누락이 있으면 그대로 실패 원인을 기록한다.
6. **기존 서비스 보호.** 기존 WhoGa 앱·Pages 경로·브랜치·이전 정상 JSON을 덮어쓰거나 삭제하지 않는다. 변경 전 구조 파악, 백업 및 회귀 테스트를 수행한다.
7. **사용자 확인 없이 임의 목표 변경 금지.** 불필요한 재작성 대신 최소 변경으로 첫 정상 수집을 통과시키고, 그다음 정기 운영을 완성한다.

### Work 완료 시 반드시 제공할 것

- 실제 수정·생성한 파일 목록과 주요 변경 사항
- GitHub 저장소, 작업 브랜치, 관련 커밋 또는 PR 링크(실제로 수행한 경우에만)
- Actions 실행 로그 링크·실행 시각·성공/실패 여부(실제로 실행한 경우에만)
- `validation.json`에 기초한 화면 표시 건수 / 수집 고유 건수 / 중복 건수 / 누락 여부
- `latest.json`·날짜별 JSON의 공개 접근 주소와 HTTP 응답 테스트 결과(실제로 배포한 경우에만)
- 실패한 경우에는 단계·원인·재현 방법·다음 수정 항목
- `README.md`·이 문서·테스트 방법 갱신

---

## 1. 변경 불가 기본 수집 URL (단일 기준점)

다음 문자열 **전체가 기본 수집 대상 URL**이다. 긴 `layer` 파라미터, `center`, `zoom`, `tradeTypes`, `realEstateTypes`를 임의로 잘라내거나 변환하지 않는다.

```text
https://fin.land.naver.com/map?center=3AoUbE-2zCmTy&zoom=18.665980292470568&tradeTypes=A1&realEstateTypes=A02&layer=NobwRAlgJmBcYGMD2BbADgGwKYA8D6UWALgIYQZgA0YaJATiSgM5zjLrY4CSMsAjABYADADYAzAFYAvtSZZ6CABYAFeoxaxwpAEZwwRBgDsmJBEQhJDVMPXMJsAFQaEHATzRYNYAIJ9rBkmNTc0tlVyxLAHM3DwA5AFcUbSw6PQAmfyMTMwtDJxIXdyw9XzAZMDpieLpDEm1sOAN4rCkAXSA
```

| 설정 | 확정값 / 정책 |
|---|---|
| 시작 URL | 위 원문 그대로 `target-url.txt`에 1줄로 저장 |
| URL 유형 | `https://fin.land.naver.com/map` |
| `center` | `3AoUbE-2zCmTy` (인코딩 문자열 원형 보존) |
| `zoom` | `18.665980292470568` |
| `tradeTypes` | `A1` — 코드 의미는 실제 UI에서 재확인 |
| `realEstateTypes` | `A02` — 코드 의미는 실제 UI에서 재확인 |
| `layer` | 원문 전체 문자열 보존 |
| 수집 시각 | 매일 오전 09:00 KST 목표; 일정 실행은 지연될 수 있음 |
| 지역 비교 | 고정된 뷰포트 및 필터 조건을 유지해 비교 가능성 확보 |
| 수집 완료 | 목록 종단 확인 + 데이터 정합성 검증 통과 |

**주의:** `center`는 일반적인 위도·경도 텍스트가 아니다. 추정으로 디코딩해 좌표를 바꾸지 않는다. 이 URL은 행정구역 경계를 확정하는 도형이 아니라 **지도 화면 및 필터의 시작 상태**다. 사용자가 선택한 범위를 유지하려면 화면 크기·축척·목록 동작을 통제해야 한다.

---

## 2. 현재 제공된 참고 매뉴얼에서 유지·수정할 내용

### 유지

- 수집 → 스냅샷 빌드 → 테스트의 **3단계 파이프라인**
- `evidence/raw-cards.json`, `evidence/dictionaries.json`, `evidence/validation.json`, `evidence/compact-snapshot.txt` 보존
- `workflow_dispatch`로 별도 URL의 **일회성 수동 실행** 지원
- `requirements.txt` 기반 Playwright·Chromium 설치
- 날짜별 스냅샷과 고정 파일명 `latest.json` 제공
- NAS Docker 실행은 선택 가능한 보조 경로로 유지

### 반드시 수정

1. `complexes/<단지번호>`를 기준으로 둔 수집기·다중 URL 예시 → **`map?...` 기본 URL 지원**으로 변경.
2. 명령어의 `"[https://...](https://...)"` 같은 **Markdown 링크 표기 오류**를 제거하고 순수 URL만 전달.
3. 기존 `python test_collector.py || echo ...` / `|| true`를 제거하여 **테스트 실패 시 발행 차단**.
4. `ls -t snapshot-*.json | head`로 예전 파일을 최신으로 오판할 가능성을 제거. **현재 실행의 출력물**을 명시적으로 선택·검증.
5. 수동 URL 실행 시 `target-url.txt`를 **영구 변경·커밋하지 않도록** 수정. 정기 수집 기준 URL을 보존.
6. GitHub Actions의 기본 `GITHUB_TOKEN`으로 커밋한 변경은 **별도의 Pages 브랜치 자동 빌드를 유발하지 않을 수 있으므로**, 같은 워크플로 내에서 **Pages artifact 직접 배포**를 적용하거나 기존 배포 워크플로와 안전하게 통합.
7. NAS의 Personal Access Token을 DSM 스케줄러 스크립트 본문에 평문 저장하지 않음. 권한이 제한된 보안 저장소·파일 또는 플랫폼 시크릿 사용.
8. GitHub Pages 공개 저장 여부, 네이버 사이트의 이용약관·robots·접근 제한·개인정보 등 법적·운영상 제약 검토.

---

## 3. Work 실행 절차 및 우선순위

### P0 — 기존 소스·저장소 실사 (코드 수정 전에 실행)

- GitHub 연동 저장소에서 `whoga-naver-collector`, WhoGa 웹앱과 Pages 배포 구성을 검색한다. 저장소명·소유자·브랜치는 **실제 조회 결과**만 사용한다.
- 제공된 `whoga-naver-collector.zip`이 실제 존재하면 파일 목록을 열어 비교한다. 제공되지 않았으면 자동으로 있다고 가정하지 않는다.
- 다음 항목을 체크한다.
  - `collector.py`가 `fin.land.naver.com/map`에 접속하는가?
  - Playwright 사용 여부, headless 실행 여부, Chromium 설치 버전 호환성은?
  - HTML DOM 카드 추출인지, 페이지의 정상 네트워크 응답 처리인지?
  - 어떤 스크롤 컨테이너를 찾아 반복하는가?
  - 리스트의 실총건수와 고유 카드 수를 어떤 방식으로 검증하는가?
  - 현재 스냅샷 JSON 스키마와 WhoGa 앱이 기대하는 필드는?
  - Actions/Pages에 이미 동작 중인 워크플로·정적 사이트가 존재하는가?
- 초기 구조·리스크를 짧게 기록하고, 기존 스냅샷 및 사이트를 백업한다.

### P1 — 로컬/Actions 최소 수집 실험

- 제공 URL을 기본 대상으로 브라우저에 접속하여 **실제 화면**과 DOM/네트워크 흐름을 관찰한다.
- 안정적인 고정 뷰포트를 채택한다. 시작값은 **데스크톱 1440×900**을 후보로 비교하되, 원래 사용자가 본 매물 패널과 지역이 달라지면 모바일 뷰포트 등 실제로 동일 조건을 재현하는 설정으로 확정한다. 최종 뷰포트를 증거에 기록한다.
- URL 이동 후 지도 및 목록이 **완전히 준비되었는지** 확인한다. 임의 `sleep`만으로 완료를 단정하지 않는다.
- 실제 목록 스크롤 컨테이너(페이지 본문이 아닐 수 있음)를 찾아 점진적으로 끝까지 내린다. 기존 관찰의 30건 단위 로딩은 **검증해야 할 동작**이지 모든 환경에서 보장되는 규칙으로 하드코딩하지 않는다.
- 가상화(virtualized list)로 DOM에는 보이는 카드만 남는 구조라면 스크롤 과정에서 신규 매물을 **즉시 누적**한다. 이전 카드가 DOM에서 사라져도 누락되지 않아야 한다.
- 중복 매물은 안정적인 매물 ID를 우선 기준으로 제거한다. ID가 없으면 근거 있는 임시 식별키를 사용하되 키 충돌 가능성을 기록한다.
- 공개 UI에서 정상적으로 접근 가능한 데이터만 수집한다. CAPTCHA·로그인·접근 거부를 우회하기 위한 계정 도용, 프록시 회전, 탐지 회피 기술을 사용하지 않는다.
- 불필요한 동시 요청을 줄이고 적절한 지연·지수 백오프·상한 시간을 적용한다. 접근 제한 발생 시 안전하게 종료하고 근거를 저장한다.

#### 권장 수집 종료 조건

1. 목록 UI의 끝 도달 신호, 총건수, 스크롤 높이/위치 또는 페이지네이션 상태를 근거로 확인.
2. 새 고유 매물 ID 수 증가가 중단되고, 추가 로딩 활동이 종료됨을 일정 횟수 재확인.
3. 화면 총건수가 **신뢰할 수 있는 고유 매물 총건수**이면 해당 수와 실제 추출 고유 매물 건수가 일치해야 성공.
4. 총건수가 매물 종류별 합계·중복 포함·상한·추정치 등으로 정밀 비교가 불가능하면 그 차이를 기록하고 `completeness=unknown`으로 처리. **100%라고 주장하지 않음.**
5. 30/60건만 들어왔어도 명확한 끝 증거 없이 성공 처리 금지.

### P2 — 파이프라인·데이터 품질 강화

1. `collector.py`: 원본 URL, 실행 ID, 타임스탬프, 선택 뷰포트, 화면 총건수, 원시 카드, 실패 증거 생산.
2. `build_snapshot.py`: 동일 실행의 `raw-cards.json`으로 최종 스냅샷 작성. 기존 앱의 JSON 스키마를 우선 유지.
3. `test_collector.py`: 고유 ID, 필드 타입, 수집 시각, 실제 실행의 원본 URL, 총건수, 중복 및 누락·빈 목록을 검사하고 **비정상 시 0이 아닌 종료 코드** 반환.
4. 모든 결과는 `run_id`로 묶어 **이전 실행의 잔존 파일이 섞이지 않도록** 함. 예: `run_id=20261019T000000Z-<short_sha>`.
5. 같은 날짜에 수동 실행을 여러 번 하더라도 기존 일일 기록을 조용히 덮어쓰지 않는다. 정기 실행은 날짜 단위 대표 스냅샷, 수동 실행은 실행 ID·URL 해시를 포함한 별도 경로를 권장.
6. 출력은 임시 경로에서 생성한 뒤 검증 성공 시에만 원자적으로 발행 디렉터리로 이동.
7. 페이지 데이터가 없거나 외부 장애로 수집 실패하면 **기존 `latest.json`을 유지하고 실패 상태만 별도 기록**. 오늘 날짜의 파일을 어제 데이터로 위장하지 않는다.

### P3 — GitHub Actions 자동화

- GitHub-hosted `ubuntu-latest` + Python + Playwright Chromium 사용.
- 정기 실행: 매일 오전 09:00 KST 목표 → `cron: '0 0 * * *'`(UTC) 또는 실제 Actions의 timezone 기능 지원 여부에 따라 등가 설정.
- 매시 정각은 GitHub 실행 혼잡으로 지연될 수 있다. 정확히 09:00 도착이 중요하지 않다면 `09:07 KST`(UTC `7 0 * * *`) 같은 분산 실행을 검토하되, **사용자가 확정한 09:00 목표를 임의 변경하지 않는다**.
- 수동 실행: `workflow_dispatch.inputs.target_url`이 비어 있으면 고정 URL, 입력되면 그 실행에서만 사용.
- 수동 URL은 `https://fin.land.naver.com/map` 형태를 기본 허용 대상으로 한다. 다른 페이지 유형 지원은 별도 명시·테스트한 후 활성화. URL 호스트 및 프로토콜은 allowlist로 검증.
- 수동 실행은 기본 `latest.json`을 덮어쓰지 않는 **시험 모드**로 운영. 승인된 기본 URL과 정확히 일치하는 정기 수집만 기본 최신 파일에 승격.
- `concurrency`로 중복 실행의 발행 경합을 방지. 단, 동시에 서로 다른 URL을 수집하도록 확장할 때는 URL별 아티팩트 분리.
- `timeout-minutes` 설정 및 화면 로딩/스크롤 로직 각각 개별 타임아웃 적용.
- 실패 시 로그, `validation.json`, 스크린샷/Trace(허용되는 정보만)를 Actions artifact로 남긴다. 민감정보와 불필요한 응답 원문 저장 금지.
- 기본 Actions 권한은 최소화하고, Git 저장·Pages 배포를 수행하는 단계에만 쓰기 권한 부여.

### P4 — GitHub Pages 배포 및 앱 연동

- 기존 Pages 배포 구조를 **먼저 조사**한다. 기존 사이트가 있다면 HTML/CSS/JS·자산을 유지하고 데이터 경로만 추가한다. 새 데이터 전용 `_site`로 기존 앱을 통째로 교체하면 안 된다.
- Git 커밋 성공 ≠ Pages 배포 성공. `actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`를 사용한 직접 배포를 우선 검토한다.
- Pages `Settings > Pages > Build and deployment > Source`는 `GitHub Actions`를 사용하도록 구성.
- 최소한 다음 공개 경로를 제공하되 **실제 저장소 이름을 조회한 후 최종 URL 확정**.
  - `https://<OWNER>.github.io/<REPO>/whoga-naver-collector/latest.json`
  - `https://<OWNER>.github.io/<REPO>/whoga-naver-collector/snapshot-YYYY-MM-DD.json`
  - `https://<OWNER>.github.io/<REPO>/whoga-naver-collector/evidence/validation.json`
  - 원시 카드 공개 필요 여부는 개인정보·라이선스 검토 후 결정.
- 정기 수집 성공 후 업데이트된 `latest.json`과 **날짜별 이력**이 Pages 빌드 아티팩트에 모두 포함됐는지 확인한다. 단일 최신 JSON만 새로 올리면 과거 파일이 삭제될 수 있음.
- `curl -fsS` 또는 HTTP 클라이언트로 공개 JSON의 HTTP 200, JSON 파싱, `run_id`/`collected_at`, 목표 URL 해시, 건수·스키마를 재검증한다. CDN 캐시 가능성을 고려해 요청에 캐시 회피 파라미터를 붙여 시험한다.
- WhoGa 앱의 기존 데이터 소비 스키마를 유지한다. 스키마 변경이 필요하면 변환/호환 계층을 추가하고 앱 배포 전후 테스트.

### P5 — Synology NAS (선택·백업)

- DS420+(RAM 6GB)는 Actions 실패 재현 및 백업 데이터 보관용으로 사용. Actions 정상화 전까지 NAS 자동 배포 중복 활성화 금지.
- Docker 이미지와 Python Playwright 패키지 **버전을 호환되게 고정**. 이미지 URL은 순수 Docker 태그를 사용하고 Markdown 링크 구문을 코드에 넣지 않는다.
- Chromium 크래시 방지를 위해 `shm_size` 등 런타임 자원 설정 테스트.
- 소스 전체를 `/app`에 바인드 마운트하면 Docker 빌드 결과를 덮어쓸 수 있으므로, 스냅샷·증거·설정은 별도 데이터 볼륨으로 분리하는 방식을 우선 검토.
- NAS 예약 작업에 GitHub PAT를 직접 평문 작성하지 말 것. 최소 범위 토큰/시크릿 보관, 디렉터리 권한 제한, 비밀정보 로그 마스킹.
- NAS 백업 수집이 GitHub Actions와 동시에 `latest.json`을 경합해 덮어쓰지 않도록 발행 주체를 하나로 유지.

---

## 4. 권장 출력 계약 — 기존 WhoGa 스키마 보존이 최우선

기존 JSON을 읽고 실제 필드명을 확인한다. 아래는 **추가 메타데이터의 권장 예시일 뿐**이며, 수집 검증을 거치지 않은 값은 채워 넣지 않는다.

```json
{
  "schema_version": "<existing-or-reviewed-version>",
  "source": "naver_fin_land_map",
  "source_url": "<exact-requested-map-url>",
  "run_id": "<generated-run-id>",
  "collected_at": "<ISO-8601-with-timezone>",
  "view": {
    "viewport_width": 1440,
    "viewport_height": 900,
    "zoom_parameter": "18.665980292470568"
  },
  "validation": {
    "status": "pass|fail|unknown",
    "visible_total_count": null,
    "unique_collected_count": null,
    "duplicate_count": null,
    "completeness": "verified|partial|unknown"
  },
  "articles": []
}
```

- 기존 WhoGa 앱이 배열형 루트 JSON을 요구하면 루트를 객체로 강제 변경하지 않는다. 메타데이터를 별도 `metadata.json`/`validation.json`으로 분리한다.
- `view`의 1440×900은 **초기 후보**이며 실제 확정 뷰포트가 아니므로 최종 실행값으로 덮어쓴다.
- 원시 매물 카드에는 화면 표시 내용, 추출 시점, stable ID, 원본 링크(허용된 경우), 수집 근거를 유지한다. 개인정보·연락처·세션 토큰은 수집/공개하지 않는다.
- 가격·면적·층·동 등 수집되지 않은 값을 추론하여 채우지 않는다. 화면 표시값과 정규화된 값을 구분.
- 시점 비교를 위해 삭제/신규/가격 변경을 판단할 때 stable ID와 비교 조건을 기록한다. 매물 부재 = 실제 거래 완료라고 단정하지 않는다.

### 검증 상태 정책

| 상태 | 의미 | 기본 최신 데이터 발행 |
|---|---|---|
| `pass` | 화면 로딩 확인, 목록 완료 증거, 필수 데이터 검증 충족 | 가능 |
| `unknown` | 화면 총건수 또는 완료 조건을 확정할 수 없음 | **차단**; 검토용 artifact만 |
| `partial` | 일부 매물만 수집·누락 가능성이 확인됨 | **차단** |
| `fail` | 수집·테스트·접근·스키마 오류 | **차단** |

실제 UI 총건수와 unique ID의 단위가 다르면 단순 숫자 일치를 성공 조건으로 사용하지 않는다. 수집 데이터 완결성을 객관적으로 입증할 수 있을 때만 `pass`.

---

## 5. GitHub Actions 권장 워크플로 **구성 예시**

> 아래는 Work가 기존 저장소를 조사한 뒤 구현할 **설계 기준**이다. `collector.py`의 실제 CLI와 Pages 빌드 구조를 확인하기 전에는 복사만으로 작동한다고 보장하지 않는다. GitHub Actions는 `ubuntu-latest`에서 Playwright Chromium을 실행할 수 있다.

```yaml
name: WhoGa Naver Map Collector

on:
  schedule:
    - cron: '0 0 * * *' # 09:00 KST 목표, 스케줄 지연 가능
  workflow_dispatch:
    inputs:
      target_url:
        description: '시험 수집 URL (비우면 기본 지도 URL)'
        required: false
        type: string
        default: ''

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: whoga-map-collect-and-publish
  cancel-in-progress: false

jobs:
  collect-and-deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    env:
      TZ: Asia/Seoul
      # URL 입력은 env로 주입하며 Bash 소스에 직접 보간하지 않음
      MANUAL_URL: ${{ inputs.target_url }}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip
          cache-dependency-path: whoga-naver-collector/requirements.txt

      - name: Install dependencies
        run: |
          python -m pip install -r whoga-naver-collector/requirements.txt
          python -m playwright install --with-deps chromium

      - name: Resolve target URL
        # Work: allowlist 검증 및 'manual/default' 분기 구현.
        # 기본 target-url.txt는 커밋하지 않을 것.
        run: python whoga-naver-collector/scripts/resolve_target.py

      - name: Collect, build and validate
        working-directory: whoga-naver-collector
        run: |
          python collector.py
          python build_snapshot.py
          python test_collector.py

      - name: Publish validated output
        # Work: 검증 성공한 현재 실행 파일만 모아서 안전하게 준비.
        # 수동 URL일 때 기존 latest.json 덮어쓰기 금지.
        run: python whoga-naver-collector/scripts/prepare_publish.py

      - name: Commit validated daily data
        # Work: 기본 URL의 정상 정기 데이터만 선별 커밋,
        # 파일 충돌·브랜치 보호·변경 없는 실행을 처리할 것.
        run: python whoga-naver-collector/scripts/commit_validated.py

      - name: Configure Pages
        uses: actions/configure-pages@v5

      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v4
        with:
          path: _site

      - name: Deploy Pages
        id: deployment
        uses: actions/deploy-pages@v4

      - name: Verify published JSON
        # Work: 실제 공개 URL HTTP 200 + JSON 내용이 이번 실행인지 검증
        run: python whoga-naver-collector/scripts/verify_pages.py

      - name: Upload debugging evidence if failed
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: whoga-collector-failure-evidence
          path: whoga-naver-collector/evidence/
          if-no-files-found: ignore
          retention-days: 7
```

**구현 시 체크:** `scripts/resolve_target.py`, `prepare_publish.py`, `commit_validated.py`, `verify_pages.py`는 이 지침에서 요구하는 **신규 제안 파일**이므로 Work가 구현하거나 기존 코드로 기능을 충족시켜야 한다. 별도 스크립트로 분리하지 않는 대안도 허용. 기존 앱에 이미 Pages 워크플로가 있다면 `environment`, `_site`, 배포 job을 그 구조에 맞춰 통합한다. 기본 `GITHUB_TOKEN`으로 `git push`한 것만으로 Pages 갱신을 기대하면 안 된다.

> 보안·실행 순서 보완: 운영에서는 배포 전 준비 작업의 실패 시 `latest.json` 변경을 막아야 하며, 가능하면 `collect`와 `deploy`를 별도 job으로 나누어 성공한 검증 artifact만 배포한다. 현재 예시는 작업 흐름을 보여주기 위한 단일-job 템플릿이다.

---

## 6. 필수 테스트 (최소 수용 기준)

| ID | 시험 | 기대 결과 |
|---|---|---|
| T01 | 고정 URL 접속 | 브라우저가 정확히 지정 URL을 열고 지도·목록 준비 확인 |
| T02 | 지도 조건 유지 | URL 파라미터와 실제 필터·뷰포트 기록 |
| T03 | 긴 목록 스크롤 | 30건/60건 초기 로드에서 멈추지 않고 종단 조건 확인 |
| T04 | 가상화 목록 | DOM에 카드가 재활용돼도 과거 발견한 매물을 잃지 않음 |
| T05 | 중복 제거 | stable ID 기준 고유 건수·중복 건수 정확 |
| T06 | 빈 목록·접근 제한 | 장애를 정상 0건으로 오판하지 않고 발행 차단 |
| T07 | 수집 후 검증 실패 | workflow 실패, 기존 `latest.json` 보존 |
| T08 | 날짜 경계(UTC/KST) | 스냅샷 날짜가 KST 기준으로 일관됨 |
| T09 | 수동 URL | 입력 URL은 그 실행에만 반영, 정기 URL 및 latest 유지 |
| T10 | 날짜별 스냅샷 | 최신 발행 뒤에도 이전 날짜 JSON 접근 가능 |
| T11 | Pages 배포 | 배포 성공 + 공개 URL HTTP 200 + 내용 최신 run_id 확인 |
| T12 | 프론트엔드 | WhoGa가 읽는 데이터 스키마·표시 내용 회귀 없음 |
| T13 | 재실행·경합 | 동일 날짜 중복 실행에도 데이터 손상/역행 없음 |
| T14 | 안전성 | 토큰, 쿠키, 개인정보가 코드·로그·공개 JSON에 포함되지 않음 |

**최종 인수 조건:** T01~T14를 실행 가능한 범위에서 실제 수행하고 근거로 체크할 것. 핵심 T01, T03, T07, T09, T11, T12는 **반드시 통과**해야 정식 운영으로 표시. 외부 정책·접근 제한으로 테스트 불가능하면 미검증으로 표시하고 배포 성공이라고 주장하지 않는다.

---

## 7. 운영 장애 대응 및 롤백

| 증상 | 우선 조사 | 대응 |
|---|---|---|
| 30건만 수집 | 실제 스크롤 컨테이너, 가상화, 다음 배치 로딩 | 데이터 누적과 종단 판정 보완 |
| 타깃 페이지가 비어 있음 | 네트워크, 차단, URL 파라미터, 필터·화면 크기 | 증거 저장 후 발행 중단 |
| 매물 총수와 불일치 | UI 집계 단위, 중복 ID, 불러오지 못한 배치 | 완결성 `unknown` 또는 `partial` |
| GitHub Actions만 실패 | headless 차이, 리소스, IP 제한, 의존성 | 공식 지원 범위 내 재현 및 원인 확인 |
| JSON 생성됐는데 Pages가 구형 | Pages 직접 배포 여부, artifact 경로, 브라우저 캐시 | Pages 재배포 + 공개 JSON 내용 확인 |
| 수동 URL이 정기 수집을 덮음 | 기본 파일 커밋 여부, output 경로 | 수동 실행 격리 및 정상 latest 복구 |
| NAS 컨테이너 실패 | 이미지/패키지 버전, 메모리, 마운트 | Docker 버전 동기화와 데이터 경로 분리 |

**롤백:** 기존 검증 완료 스냅샷을 유지하고 배포 전에 보관한 안정 커밋/Pages artifact로 복귀. 롤백 이후 앱에서 JSON 파싱과 표시를 확인한다. 수집 실패 사실을 숨기기 위해 기존 데이터를 현재 날짜로 복제하지 않는다.

---

## 8. 프로젝트 예상 디렉터리 (강제 아닌 목표 형태)

```text
<repository-root>/
├── .github/
│   └── workflows/
│       └── collector.yml
├── whoga-naver-collector/
│   ├── README.md
│   ├── requirements.txt
│   ├── target-url.txt
│   ├── collector.py
│   ├── build_snapshot.py
│   ├── test_collector.py
│   ├── scripts/                  # 필요한 경우에만
│   │   ├── resolve_target.py
│   │   ├── prepare_publish.py
│   │   ├── commit_validated.py
│   │   └── verify_pages.py
│   ├── evidence/
│   │   ├── raw-cards.json
│   │   ├── dictionaries.json
│   │   ├── validation.json
│   │   └── compact-snapshot.txt
│   ├── latest.json
│   └── snapshot-YYYY-MM-DD.json
├── instruction.md
└── [existing WhoGa site files / deployment setup]
```

- **우선:** 기존 저장소 구조와 이미 배포 중인 WhoGa 웹사이트를 훼손하지 않는다.
- **선택:** 다중 지도 URL로 확장할 때는 `targets/<slug>.txt`·`snapshots/<slug>/<date>.json`처럼 타깃별 분리. `<slug>`는 사용자가 입력한 파일 경로를 그대로 쓰지 말고 검증된 별칭/URL 해시를 사용.
- Git에 추가할 데이터와 Actions artifact만 보존할 디버그 데이터를 분리. 스크린샷·네트워크 로그의 무제한 Git 누적 금지.

---

## 9. 작업 결과 보고 서식 (Work 종료 시)

```text
[WhoGa 네이버 지도 수집기 · 실행 결과]

1. 실제 대상 저장소 / 브랜치 / 커밋:
2. 실행 환경(Playwright·Python·Chromium 버전):
3. 사용한 URL / 뷰포트 / 수집 시각(KST):
4. 확인된 화면 총건수 및 집계 근거:
5. 수집 원시 건수 / 고유 건수 / 중복 / 누락:
6. validation.status / completeness / 실패 원인:
7. GitHub Actions 실행 결과 및 로그 URL:
8. Pages 배포 결과 및 실 URL:
9. WhoGa 앱 연동 테스트 결과:
10. 적용한 수정과 미완료 항목:
11. 롤백 지점 및 재실행 방법:

※ 확인하지 못한 항목은 '미확인'으로 명시한다.
※ 실제 링크를 확보하지 못하면 추정 주소를 쓰지 않는다.
```

---

## 10. 참고 문서·공식 근거

- 사용자 제공 이전 지침서: `whoga-naver-collector 배포, URL 동적 추출 및 GitHub Pages 연동 지침서` (이 문서의 초기 초안)
- Playwright Python CI: https://playwright.dev/python/docs/ci
- Playwright Python Browser 설치: https://playwright.dev/python/docs/browsers
- Playwright Python Docker: https://playwright.dev/python/docs/docker
- GitHub Pages custom workflows: https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages
- GitHub Pages publication source: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site
- GitHub `GITHUB_TOKEN` 동작: https://docs.github.com/en/actions/concepts/security/github_token

### Work 실행 시 최종 판단 기준

**목표는 'Playwright가 실행되었다'가 아니라, '오늘 지정 지도에서 읽을 수 있는 매물을 누락 없이 수집했음을 입증하고, WhoGa가 해당 날짜 JSON을 실제로 읽을 수 있게 했다'이다.**

실측으로 확인되지 않은 사실을 성공으로 표시하지 말고, 남은 문제와 증거를 기록한다. 성공한 날의 최신 데이터만 발행한다.


## 11. 실행 부록 — 2026-10-19

실제 대상은 `PoeticEcho/whoga`, 작업 브랜치는 `map-collector-v2`, draft PR은 #2다. 원본 지침의 목표는 유지한다. 코드 변경·59개 로컬 테스트를 완료했지만 Actions의 네이버 접속과 신규 Pages 배포는 미완료다.

13시대 별도 클라우드 브라우저에서 120개를 확인했으며 운영 총수를 118 또는 120으로 고정하지 않는다. 단일 실제 ID와 묶음 임시 키를 구분하도록 수정했다. main과 기존 데이터를 바꾸지 않았으며 NAS는 미접속·미시험이다.

실제 validation.json, 실행 시각/로그, T01–T14 결과, 수정 파일과 남은 차단점은 [VERIFICATION_MAP.md](VERIFICATION_MAP.md), 실행 방법은 [수집기 README](whoga-naver-collector/README.md)를 따른다. T01/T03/T11 운영 검증이 남아 있으므로 정식 운영 성공으로 표시하지 않는다.

### 후속 실측 — 19시대

2026-10-19 19:06–19:07 KST 클라우드 브라우저 관측 120개를 두 차례 비교해 고유120/중복0/누락0을 확인했다. 실제 뷰포트는 1363×936이다. 기존 앱 JSON 변환과 임시 로컬 HTTP 이력 검증을 통과했으며 한글 파일명 URL 인코딩 오류를 수정했다. 최신 테스트는 63개 통과. 보조 관측은 publication_eligible=false로 표시하고 정기 발행에서 차단한다. Actions 실수집·공개 Pages 배포 미완료 상태는 변함없다. 상세 근거는 VERIFICATION_MAP.md의 후속 실측 절을 따른다.

### 2026-10-20 Actions 경로 비교

사용자 추가 첨부 v2의 검사와 실제 GitHub Actions 비교를 수행했다. Windows tzdata 누락을 수정했으나 Edge, 첨부 Chromium headed/headless, Firefox, WebKit 모두 첫 문서 응답 단계에서 실패했다. 세부 결과·로그·자체 실행기 등 남은 조건은 ACTIONS_REVIEW.md에 기록했다. 정기 발행 활성화나 기존 서비스 데이터 교체는 하지 않았다.
