# whoga · W 호가 · GitHub Pages 배포본 v1.0.0

날짜별 호가를 확인하는 웹페이지와, 매일 수집·저장·텔레그램 발송하는 GitHub Actions를 함께 제공합니다.
별도 PHP 서버나 데이터베이스는 필요하지 않습니다.

**현재 포함된 자료는 첨부받은 기준 자료입니다. 실제 네이버 자동 수집 성공을 뜻하지 않습니다.**
첫 실행에서 수집이 성공하는지 확인한 뒤 매일 알림을 활성화하세요.

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

화면에서 기본값은 `2026-10-17(120건)`과 이전 날짜 `2026-10-16(117건)`입니다.
같은 날짜의 118건 자료도 별도 선택할 수 있습니다.

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
로그인·CAPTCHA·접근 제한을 우회하는 쿠키·토큰·TLS 위장 기능은 넣지 않았습니다.

수집 실패 시 기존 날짜별 JSON을 유지하고 상태만 실패로 기록합니다.
**미수집을 ‘오늘 변동 없음’으로 표시하지 않습니다.**
현재 자료가 없다는 사실만으로 실제 매물 0건으로 덮어쓰지 않습니다.

## 3. 텔레그램 알림 연결

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

이제 매일 **한국시간 오전 8:13 전후**에 수집·저장·배포·알림을 처리합니다.
`ENABLE_DAILY=true`만 설정하면 웹 자료만 갱신하며, 텔레그램 알림은 `ENABLE_TELEGRAM=true`일 때 발송합니다.
GitHub 대기열에 따라 실행이 늦어지거나 누락될 수 있습니다.
공개 저장소에서 60일 동안 활동이 없으면 GitHub가 예약 실행을 비활성화할 수 있습니다.
정기적으로 Actions 실행 기록을 확인하세요. 중단하려면 `ENABLE_DAILY`를 `false`로 바꾸면 됩니다.

같은 날짜·같은 자료·같은 수신 대화에는 성공 알림을 중복 발송하지 않습니다.
실패 알림은 날짜별로 중복을 억제합니다. 같은 날 복구한 뒤 성공하면 성공 알림을 별도로 보냅니다.
발송 응답을 받지 못했을 때는 자동 재전송하지 않습니다.
텔레그램 발송 직후 Git 상태 기록이 실패하는 경우까지 ‘정확히 한 번’을 보장하지는 않습니다.

## 4. 비교 결과 읽기

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
| 2026-10-17 | 120 | 120 | 기본 기준 자료 |
| 2026-10-17 (118건) | 118 | 118 | 같은 날 별도 자료 |
| 2026-10-16 | 117 | 117 | 기본 비교 자료 |
| 2026-08-06 | 108 | 92 | 일부 자료로 표시, 신규·미관측 비교 제외 |

## 5. 자동 수집이 실패할 때

2026-10-18 실제 실행에서 `page.goto(..., wait_until="commit")`가 45초 안에 완료되지 않았습니다.
매물 해석을 시작하기 전의 실패이며, 이 결과만으로 DNS·서버·보안 연결 문제나 접근 제한을 확정할 수 없습니다.
`Actions → whoga · 네이버 연결 진단`은 설정된 공개 원문에 한 번 요청해 DNS·TCP·TLS·첫 응답 시간을 기록합니다.
이 진단은 수집 자료·알림을 변경하지 않으며, 자동 재시도나 인증서 검증 해제는 하지 않습니다.

일일 운영은 실제 수집 성공을 확인한 뒤 활성화합니다. 현재 화면에는 `자동 갱신 연결 점검 중`을 표시합니다.
GitHub 실행 환경에서 연결이 계속 실패하면, 정상 접근 가능한 본인 컴퓨터에서 기존 수집기를 먼저 시험할 수 있습니다.
로컬 시험도 성공을 확인해야 하며 컴퓨터의 정기 실행 설정과 공유 자료 갱신 연결이 필요합니다.

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
네이버 원문 접근과 전체 매물 수집은 실행 환경·페이지 변경에 영향을 받습니다. 첫 실제 수집 성공을 확인한 뒤 일일 운영을 켜세요.

공식 참고: [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages), [Pages 배포 워크플로](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [예약 실행](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule), [Actions Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets), [Telegram Bot API](https://core.telegram.org/bots/api#sendmessage).
