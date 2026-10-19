# whoga · W 호가 · GitHub Pages 배포본 v1.0.0

> **2026-10-20 추가 검토:** [첨부 v2 및 Actions 실행 경로 검토](ACTIONS_REVIEW.md). Windows 시간대 오류 수정 후 실제 수집 재시험, 첨부본 headed/headless 및 Firefox/WebKit 시험을 완료했지만 모두 문서 접속 단계에서 실패했습니다. 운영 데이터는 유지합니다.

> **2026-10-19 지도 수집기 v2 작업:** [수집기 사용법](whoga-naver-collector/README.md) · [실제 검증 결과](VERIFICATION_MAP.md) · [draft PR #2](https://github.com/PoeticEcho/whoga/pull/2). 클라우드 브라우저 실측 120개를 두 차례 검증했고 기존 앱 형식 변환·로컬 HTTP 연동을 통과했습니다. 테스트는 64개 통과. Actions 실수집은 접속 실패 상태이며 신규 Pages 배포와 정기 운영은 아직 완료하지 않았습니다. 아래 내용은 기존 v1 운영 안내입니다.

날짜별 호가를 확인하는 웹페이지와 수집·검증 도구를 제공합니다. 현재 알림은 ChatGPT 예약 작업을 사용합니다.
별도 PHP 서버나 데이터베이스는 필요하지 않습니다.

**2026-10-18 클라우드 브라우저에서 매물 패널을 스크롤해 118개 전체를 수집·검증했습니다.**
첫 화면 30개 → 60개 → 90개 → 118개로 로딩됐고, 원문 총수·상세 카드 수·필수 항목 수가 일치했습니다.
Firecrawl 기본 scrape는 첫 30개를 읽었으나 interact 세션은 일반 404로 이동해 전체 수집이 확인되지 않았습니다.
GitHub Actions 직접 수집도 연결 시간 초과 상태이므로 일일 수집 변수는 활성화하지 않았습니다.

## 1. 웹페이지 먼저 열기

1. GitHub에서 `whoga`라는 이름의 빈 저장소를 만듭니다. 이름은 W 호가를 뜻합니다.
   GitHub Free에서 Pages를 이용하려면 공개(Public) 저장소를 선택합니다. 공개 저장소의 파일은 누구나 볼 수 있습니다.
2. ZIP을 풀어 **이 README와 같은 위치의 파일·폴더 전체**를 저장소의 `main` 브랜치에 업로드합니다.
   ZIP 파일 자체를 올리는 방식은 실행되지 않습니다.
3. `.github/workflows/daily_briefing.yml`도 업로드되었는지 확인합니다.
   휴대폰 파일 앱에서 `.github`가 보이지 않으면 숨김 파일 표시를 켜세요.
   브라우저에서 직접 만들려면 `Add file → Create new file`을 누르고 파일명을
   `.github/workflows/daily_briefing.yml`로 입력한 뒤 패키지의 같은 파일 내용을 붙여넣습니다.
4. 저장소 `Settings → Pages → Build and deployment → Source`를 **GitHub Actions**로 선택합니다.
   `Deploy from a branch`를 선택하지 않습니다.
5. `Actions → whoga · W 호가 & Pages → Run workflow`를 실행합니다.
   첫 실행에서는 **collect, notify 두 항목 모두 체크하지 않습니다.**
6. 작업이 끝나면 배포 단계에 나오는 URL로 접속합니다.
   `PoeticEcho/whoga` 저장소의 예정 주소는 `https://poeticecho.github.io/whoga/`입니다. 실제 공개 여부는 배포 작업 결과에서 확인합니다.

현재 기본 자료는 `2026-10-18(118건)` 실제 관측입니다. 10월 17일·16일의 제공 자료도 날짜별로 보존합니다.

### ChatGPT 예약 작업

`범어W 호가 확인`을 한국시간 매일 아침 8시 무렵에 실행하도록 등록했습니다.
클라우드에서 수집을 시도하고 결과를 ChatGPT로 전달합니다. 휴대폰·PC를 켜둘 필요가 없습니다.
Firecrawl 스크롤 경로가 실패하면 제공되는 정상 클라우드 브라우저에서 매물 패널을 직접 스크롤하도록 절차를 기록했습니다.
전체 검증 성공 때만 데이터를 갱신하고, 부분 수집·실패일에도 상태를 보고합니다.
예약 등록은 매일 수집 성공을 보장하지 않습니다. 예약 작업의 실행 결과와 사이트 기준일을 확인하세요.

Firecrawl interact에서 사용할 JavaScript는 `scripts/listing_dom.js` 다음에
`scripts/firecrawl_scroll.mjs`의 내용을 이어 붙입니다. 같은 scrapeId에서 `language=node`, `timeout=30`으로 실행합니다.
공식 런타임의 `page`를 사용하며 자연어 에이전트가 링크를 클릭하지 않습니다.
반환 stdout JSON의 `complete`, `progress`, `text`를 확인하고 파서로 다시 검증해야 합니다.
일반 404·로그인·접근 제한 화면에서는 수집 성공으로 저장하지 않습니다. 세션은 사용 후 닫습니다.

## 2. 네이버 실제 수집 확인

1. 같은 `Run workflow`에서 **collect만 체크**합니다. notify는 체크하지 않습니다.
2. `Collect complete snapshot` 단계가 성공하는지 확인합니다.
3. `data/YYYY-MM-DD.json`과 `data/status.json`이 갱신됐는지 확인합니다.
   같은 날짜의 성공한 새 수집은 그 날짜 파일을 갱신합니다. 이전 내용은 Git 이력에 남습니다.
4. 웹페이지를 새로고침해 자동 수집 출처·기준일·수량이 표시되는지 확인합니다.

수집 방식은 공개 페이지에 표시되는 공동중개 묶음 목록을 관측하는 방식입니다.
개별 중개사 JSON의 건수와 화면의 묶음 건수를 혼합하지 않습니다.
네이버의 페이지 구조·타입·동 필터·목록 묶음 방식이 달라지면 파서 조정이 필요할 수 있습니다.
페이지 전체 총수와 대상 오피스텔 목록의 수량이 맞지 않으면 성공으로 저장하지 않습니다.
운영 수집기는 일반 Playwright 브라우저를 사용하며 로그인·CAPTCHA·접근 제한 화면에서 중단합니다.

수집 실패 시 기존 날짜별 JSON을 유지하고 상태만 실패로 기록합니다.
**미수집을 ‘오늘 변동 없음’으로 표시하지 않습니다.**
현재 자료가 없다는 사실만으로 실제 매물 0건으로 덮어쓰지 않습니다.

## 3. 텔레그램 알림 연결 (선택 사항, 현재 미설정)

1. 텔레그램 `@BotFather`에서 봇을 만들고 Bot Token을 발급받습니다.
2. 알림을 받을 계정에서 그 봇과 대화를 시작합니다. 필요한 경우 `/start`를 보냅니다.
3. 그 대화의 Chat ID를 확인합니다. 봇 API `getUpdates`를 사용할 경우 토큰이 포함된 URL을 타인에게 공유하지 마세요.
4. GitHub `Settings → Secrets and variables → Actions → Secrets`에 다음 2개를 등록합니다.

| 이름 | 값 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | 봇 토큰 |
| `TELEGRAM_CHAT_ID` | 수신 대화 ID |

5. `Run workflow`에서 **notify만 체크**하면 현재 최신 자료의 알림을 시험할 수 있습니다.
   제공 자료이면 알림에도 제공·수동 입력 자료라고 표시합니다. 실제 새 수집 시험은 collect도 함께 체크합니다.
6. 메시지가 도착한 다음 `Variables` 탭에 `ENABLE_DAILY` = `true`, `ENABLE_TELEGRAM` = `true`를 등록합니다.

아래 GitHub 일일 운영을 별도로 활성화하면 **한국시간 오전 8:13 전후**에 수집·저장·배포·알림을 시도합니다.
`ENABLE_DAILY=true`만 설정하면 웹 자료만 갱신하며, 텔레그램 알림은 `ENABLE_TELEGRAM=true`일 때 발송합니다.
GitHub 대기열에 따라 실행이 늦어지거나 누락될 수 있습니다.
공개 저장소에서 60일 동안 활동이 없으면 GitHub가 예약 실행을 비활성화할 수 있습니다.
정기적으로 Actions 실행 기록을 확인하세요. 중단하려면 `ENABLE_DAILY`를 `false`로 바꾸면 됩니다.

같은 날짜·같은 자료·같은 수신 대화에는 성공 알림을 중복 발송하지 않습니다.
실패 알림은 날짜별로 중복을 억제합니다. 같은 날 복구한 뒤 성공하면 성공 알림을 별도로 보냅니다.
발송 응답을 받지 못했을 때는 자동 재전송하지 않습니다.
텔레그램 발송 직후 Git 상태 기록이 실패하는 경우까지 ‘정확히 한 번’을 보장하지는 않습니다.

## 4. 비교 결과 읽기

### 브리핑·텍스트 목록

- `브리핑` 탭에서 **요약·변동 / 모닝 브리핑 / 변동 리포트 / 전체 매물**을 선택하고 `내용 복사` 또는 `TXT 저장`을 누릅니다.
- 모닝 브리핑에는 실제 한국시간 관측 시각, 타입별 건수·최저·중앙값, 동별 건수·타입별 가격 범위를 표시합니다. 관측 시각이 없으면 날짜만 표시합니다.
- 동별 **호가 범위**의 상단은 원본의 최대 호가, 중앙값은 각 행의 최소 호가로 계산합니다. 별도의 시장 심리 해석은 넣지 않습니다.
- 변동 리포트는 추가 관측·미관측·매물번호 일치 가격 변동·조건 일치 변동 후보를 각각 모두 표시합니다. 전일 자료가 아닐 때는 실제 비교 기준일을 적습니다.
- `매물 목록 → 보기 방식 → 텍스트 보기`는 현재 필터와 정렬을 반영해 동·타입별로 정리합니다. 기본은 최저 호가순입니다. `목록 복사`와 `TXT 저장`을 지원합니다.
- 한 행은 `101동/78/27층/6.20억/11곳` 형식입니다. 범위 호가·실제 층수·같은 조건의 별도 행을 보존하고, 단독 중개사명은 자료에 있을 때만 표시합니다.
- 필터 결과를 복사하면 전체 기준 자료와 필터 건수를 구분합니다. 텍스트에서는 같은 조건 묶기를 적용하지 않습니다.
- Python 알림용 `build_briefing`과 웹의 요약·변동 출력은 같은 형식이며 실제 자료를 이용한 일치 검사를 수행합니다.

| 표시 | 의미 |
|---|---|
| 추가 관측 | 비교 자료에 대응되는 조건·번호가 없었던 관측 행 |
| 번호 확인 변동 | 같은 네이버 매물번호의 최소 또는 최대 호가가 달라짐 |
| 변동 후보 | 번호가 없고 동·타입·층·향이 1:1로 대응되는 조건의 가격 차이. 같은 호수인지 확인 필요 |
| 미관측 | 이전 자료에 있던 행을 이번 자료에서 찾지 못함. 거래 완료로 단정하지 않음 |
| 같은 조건 유지 | 번호 또는 동일 조건·가격으로 대응되는 관측 행. 번호가 없으면 동일 호수를 뜻하지 않음 |
| 같은 조건 묶기 | 화면에서 동일 조건·가격을 묶어 표시. 실제 중복 제거가 아님 |

가격 범위가 있는 매물의 최저·중앙값·평균·최고 통계는 각 행의 **최소 호가**를 기준으로 계산합니다.
원본의 최대 호가도 보존하고 목록·변동 비교에 사용합니다.
원문 총수와 일치하더라도 데이터의 사실성이나 동일 호수 식별을 100% 보장하지는 않습니다.
첨부 자료의 `item_1` 같은 순번은 네이버 매물번호로 취급하지 않습니다.

첨부된 과거 자료는 4개 모두 보존했습니다.

| 기준 자료 | 원문 총수 | 상세 행 | 처리 |
|---|---:|---:|---|
| 2026-10-18 | 118 | 118 | 클라우드 브라우저 실제 관측·전체 검증 |
| 2026-10-17 | 120 | 120 | 기본 기준 자료 |
| 2026-10-17 (118건) | 118 | 118 | 같은 날 별도 자료 |
| 2026-10-16 | 117 | 117 | 기본 비교 자료 |
| 2026-08-06 | 108 | 92 | 일부 자료로 표시, 신규·미관측 비교 제외 |

## 5. 자동 수집이 실패할 때

2026-10-18 실제 실행에서 `page.goto(..., wait_until="commit")`가 45초 안에 완료되지 않았습니다.
매물 해석을 시작하기 전의 실패이며, 이 결과만으로 DNS·서버·보안 연결 문제나 접근 제한을 확정할 수 없습니다.
`Actions → whoga · 네이버 연결 진단`은 설정된 공개 원문에 한 번 요청해 DNS·TCP·TLS·첫 응답 시간을 기록합니다.
이 진단은 수집 자료·알림을 변경하지 않으며, 자동 재시도나 인증서 검증 해제는 하지 않습니다.

`Actions → whoga · 통신 호환성 비교`에서는 같은 공개 원문을 HTTP/1.1 및 `curl-cffi==0.16.3`의 Chrome 통신 프로필로 각각 한 번 시험합니다.
명시적인 제한 응답이면 다음 방식을 실행하지 않습니다. HTTP 응답 성공과 HTML 본문의 전체 매물 수량 일치 여부를 따로 기록합니다.
비교 시험은 운영 수집기와 분리되어 있으며 자료·알림을 변경하지 않습니다. 인증 쿠키·프록시·IP 순환은 사용하지 않습니다.

사용자 모바일 화면은 지도 없이 단지·매물 목록을 보여 줍니다. 기존 PC 크기 수집과 구분하여
`Actions → whoga · 모바일 목록 수집 시험`에서 표준 Pixel 7 화면으로 같은 주소를 검사할 수 있습니다.
실행 명령은 `python crawler.py --mobile --dry-run`이며 첫 응답·화면 목록 수량만 확인하고 자료·알림을 변경하지 않습니다.
모바일 화면에서도 전체 수량과 필수 항목 검사를 통과해야 성공으로 판정합니다.

GitHub Actions 직접 일일 수집은 해당 환경에서 성공을 확인한 뒤 활성화합니다.
현재 운영 경로는 ChatGPT 예약 작업의 클라우드 수집 시도입니다.
목록 수집기는 매물 패널 하단까지 내린 뒤 추가 로딩을 기다립니다. 하단에 도착하기 전의 수량 정체로 종료하지 않습니다.
동일 원문 총수·카드 수·해석 수량이 두 차례 연속 일치해야 성공하며, 수집 도중 원문 총수가 바뀌면 보류합니다.

웹페이지 `수동 자료`에서 JSON을 가져오거나, 총수와 각 매물의 내용을 포함한 네이버 원문을 붙여넣을 수 있습니다.
이 자료는 **그 브라우저에만 저장**됩니다. 다른 기기·매일 알림에는 자동 반영되지 않습니다.

공유 자료에 반영하려면 웹페이지에서 날짜별 JSON을 내려받은 뒤 로컬에서 다음 명령으로 등록하고 GitHub에 올리세요.

```bash
python crawler.py --input /path/to/snapshot.json --dry-run
python crawler.py --input /path/to/snapshot.json
# 같은 날짜를 의도적으로 교체할 때
python crawler.py --input /path/to/snapshot.json --replace
```

JSON이 아닌 복사 원문 파일은 다음처럼 사용합니다.

```bash
python crawler.py --input /path/to/naver-copy.txt --date 2026-10-18
```

수동 입력도 수량·필수 항목 검사를 통과해야 날짜별 JSON으로 저장됩니다.
`data/` 변경을 GitHub에 커밋하면 배포 작업이 실행됩니다.
알림을 보내려면 `Run workflow`에서 notify를 선택합니다.

## 6. 내 컴퓨터에서 확인·실행

Python 3.11 이상, 검증용 Node.js 22 이상을 사용합니다.

```bash
python -m unittest discover -s tests -v
node --test tests/*.test.mjs
python scripts/build_site.py
python -m http.server 8000 --directory _site
```

브라우저에서 `http://localhost:8000`에 접속합니다.
`index.html`을 파일로 직접 열면 JSON 요청이 브라우저 보안 정책으로 차단될 수 있습니다.

실제 수집을 실행하려면 추가 설치가 필요합니다.

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python crawler.py
```

GitHub Actions에서는 브라우저와 Linux 의존성까지 자동 설치합니다.
알림 내용을 발송 없이 확인하려면 `python scripts/notify.py --dry-run`을 사용합니다.

## 7. 구성과 설정

| 경로 | 역할 |
|---|---|
| `index.html`, `assets/` | 모바일·태블릿·PC용 정적 화면. 외부 폰트·차트·CSS CDN 불필요 |
| `data/YYYY-MM-DD.json` | 날짜별 자료 |
| `data/index.json` | 날짜 목록. 빌드·수집 때 재생성 |
| `data/status.json` | 최근 수집 성공·실패·시도 시각 |
| `config.json` | 공개 가능한 단지·페이지 설정. 비밀값 입력 금지 |
| `monitor.py`, `crawler.py` | 검증·비교·수집·저장 |
| `scripts/listing_dom.js` | 매물 패널 읽기·하단 스크롤 공통 코드 |
| `scripts/firecrawl_scroll.mjs` | Firecrawl interact용 제한 시간 내 스크롤 배치 |
| `scripts/notify.py` | 텔레그램 알림 |
| `_state/notifications.json` | 성공한 알림의 중복 억제 키. 최초 발송 때 생성, 웹 배포 제외 |
| `scripts/build_site.py` | 공개 파일만 `_site/`로 구성 |
| `.github/workflows/daily_briefing.yml` | 일일 실행과 Pages 배포 |
| `tests/` | 오탐·부분 수집·실패 보존·알림 검증 |

토큰·DB 비밀번호·쿠키는 소스 코드, `config.json`, 브라우저 저장소에 넣지 않습니다.
단지 ID는 이 패키지에서 제공받은 `140635`를 사용합니다. 다른 단지를 감시하려면 타입·동·원문 파서도 함께 조정해야 합니다.
`main` 이외의 브랜치로 운영하려면 워크플로의 push 브랜치와 두 곳의 `HEAD:main`, 알림 checkout의 `ref: main`을 함께 바꾸세요.

## 8. 검증 범위와 남은 확인

포함된 기준 자료와 합성 입력으로 데이터·비교·저장·알림 실패 처리를 검사했습니다.
화면 동작은 DOM 모의 환경과 배포된 공개 페이지의 실제 브라우저에서 검사했습니다.
날짜 전환·필터·검색·초기화 및 CSV·JSON 다운로드를 확인했습니다.
텔레그램 시험은 모의 응답으로 검증하며 실제 메시지를 발송하지 않았습니다.
`PoeticEcho/whoga` 저장소와 `https://poeticecho.github.io/whoga/` 배포를 완료했습니다.
2026-10-18 06:35 KST 실제 수집 실행은 최초 응답 시간 초과로 실패했고, 저장된 자료 보존과 재배포는 확인했습니다.
2026-10-18 클라우드 브라우저 실제 관측은 118/118개 검증을 통과했습니다(78OB 71개, 84OA 47개).
스크롤 회귀 검사는 긴 목록의 수량 정체, 하단 부분 수집 거부, 수집 중 총수 변경 거부를 확인합니다.
Firecrawl interact 전체 수집과 예약 작업의 반복 성공은 아직 확인되지 않았습니다. 실행 환경·페이지 변경에 영향을 받습니다.

공식 참고: [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages), [Pages 배포 워크플로](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [예약 실행](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [Actions Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets), [Telegram Bot API](https://core.telegram.org/bots/api#sendmessage).
