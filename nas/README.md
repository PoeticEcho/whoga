# WhoGa NAS · DS420+ 관리 화면 v1.1

접속 주소: **http://NAS주소:8899**

감시할 단지 주소, 실행 간격, 즉시 검사·전체 수집, 로그, GitHub 연결 확인·업로드 상태를 한 화면에서 관리한다. DS420+ / linux/amd64 / Container Manager용이다.

## 설치 파일 구조

압축을 `/volume1/docker/whoga`에 풀면 아래 폴더가 있어야 한다.

- `nas/`: 관리 화면, Dockerfile, compose.yaml, setup.sh
- `experiments/supplied-v2/`: 기존 수집기 및 버전 고정 requirements
- `collector-runs/nas/`: 실행 후 생성되는 로그·결과
- `nas-config/`: 실행 후 생성되는 설정·GitHub 토큰 (공개 금지)

기존 1.0 설치자는 실행 중인 단발 컨테이너를 종료한 뒤 파일을 교체한다. 기존 .env에 DASHBOARD_PASSWORD가 없다면 12자 이상 비밀번호를 추가해야 한다. 기존 결과는 삭제하지 않는다.

## 가장 빠른 설치

1. DSM 패키지 센터에서 Container Manager 설치.
2. 설치 ZIP을 File Station으로 올려 `/volume1/docker/whoga`에 압축 해제. 중첩 폴더 없이 그 아래 nas 폴더가 있어야 한다.
3. 일반 NAS 계정의 SSH 터미널에서 실행:

```sh
cd /volume1/docker/whoga/nas
sh setup.sh
```

최초 실행 시 계정 `admin`과 무작위 관리 비밀번호가 표시된다. 비밀번호는 `nas/.env`에도 보관된다. Docker 접근 권한 오류가 나면 설정 파일을 다시 만들지 말고 아래 Docker 명령에만 관리자 권한을 적용한다.

```sh
cd /volume1/docker/whoga/nas
sudo docker compose up -d --build
```

`setup.sh` 전체를 root로 실행하지 않는다. 컨테이너는 NAS 폴더 소유자의 일반 UID/GID로 실행해야 Chromium 샌드박드가 동작한다. 파일 권한 문제는 해당 전용 폴더의 소유권과 DSM ACL을 확인한다. `chmod 777`로 공유폴더 전체를 개방하지 않는다.

4. 브라우저에서 `http://NAS주소:8899` 접속 → 계정 `admin`, 위 비밀번호 입력.

Container Manager 프로젝트 UI를 쓰는 경우 `nas`를 프로젝트 경로로 선택하고 `compose.yaml`을 사용한다. 최초 .env와 쓰기 가능한 두 결과 폴더는 먼저 준비해야 한다.

### 수동 설정 대안

SSH에서 `id -u`와 `id -g` 값을 확인한 뒤 `nas/.env`를 만든다. 아래 자리표시자는 실제 값으로 바꾼다.

```dotenv
NAS_UID=일반계정_UID
NAS_GID=일반계정_GID
DASHBOARD_PASSWORD=12자_이상의_새_비밀번호
NAS_BIND_IP=0.0.0.0
```

NAS_BIND_IP를 NAS의 내부 IP로 지정하면 해당 인터페이스에만 연결한다. DSM 방화벽 사용 시 내부망에서 TCP 8899 접속을 허용한다. 인터넷 포트포워딩으로 공개하지 않는다. 외부 접속이 필요하면 VPN 또는 인증을 유지한 HTTPS 리버스 프록시를 사용한다. HTTP에서는 비밀번호·설정 전송이 암호화되지 않는다.

## 첫 시험 순서

1. **브라우저 확인** → `브라우저 정상`: 외부 페이지 접속 없이 컨테이너와 샌드박드 확인.
2. **감시 설정** → `https://fin.land.naver.com/complexes/140635` → 설정 저장.
3. **표본 검사** → 처음 3개 카드와 중개사 묶음 확인.
4. **전체 수집** → 같은 실행에서 표본 검사를 다시 통과하면 전체 수집.
5. 카드 수·개별 매물 수·로그를 확인하고 GitHub를 연결.

단지 주소 한 개를 감시한다. 주소에는 쿼리나 지도 좌표를 붙이지 않는다. 화면에서 단지번호와 매매 필터를 확인한다. 지정 주소는 네이버 단지 경로만 허용하며 임의 내부망 URL은 받지 않는다.

전체 수집을 누른 뒤에도 표본 검사에서 실패하면 전체 단계로 넘어가지 않는다. 중복 실행 방지, 실행 중지, 30분 제한, 재시작 시 중단 표시가 포함된다. 실패를 정상 0건으로 표시하지 않는다.

## GitHub 설정

화면의 **GitHub 업로드 설정**을 펼친다.

- 저장소: 기본 `PoeticEcho/whoga`
- 기존 브랜치: 기본 `map-collector-v2`
- 토큰: 해당 저장소만 선택한 fine-grained PAT, `Contents: Read and write`
- `설정 저장` → `저장된 설정으로 연결 확인`

연결 확인은 브랜치 읽기만 검사한다. 쓰기 권한과 브랜치 보호 규칙은 실제 업로드 때 검증한다. 토큰은 `nas-config/settings.json`에 0600 권한으로 저장하며, API·화면·수집 프로세스에 전달하지 않는다. 빈 토큰 입력은 기존 값을 유지하고, 삭제 체크를 하면 제거한다. 이 폴더와 .env를 GitHub에 올리지 않는다.

전체 수집 통과 후 **GitHub 업로드** 버튼으로 현재 실행의 결과를 저장한다. 선택한 저장소가 공개라면 업로드 자료도 공개된다. 자동 업로드는 기본 꺼짐이며 직접 켤 수 있다.

업로드 경로: `nas-imports/<단지번호>/<runId>.json`

업로드 상태는 실행 중/완료/실패로 표시하고 완료 시 파일 링크를 제공한다. 기존 파일을 덮어쓰지 않는다. 업로드 버튼은 현재 주소의 전체 수집 결과가 있을 때만 활성화된다.

**이 업로드는 검증 자료 전달이다. WhoGa 운영 데이터와 Pages를 자동 갱신하지 않는다.** 현재 첨부본 수집기의 카드/매물 스키마는 운영 앱과 다르며, 가상화 목록의 2회 전수 관측·운영 스키마 변환·발행 검증이 추가로 필요하다. 산출물에는 `publicationEligible=false`를 유지한다.

## 주기 실행과 파일

- 기본 꺼짐. 켜면 설정 저장 시점부터 지정 간격마다 전체 수집한다.
- 범위 15~10080분, 기본 1440분(24시간). 매일 고정 시각 09시 기능은 아니다.
- 컨테이너 재시작 시 다음 실행은 다시 한 간격 뒤로 잡는다. 놓친 실행을 몰아서 수행하지 않는다.
- Docker는 재부팅 후 자동 시작(`unless-stopped`), 수집 일정은 저장 설정을 따른다.
- NAS 작업 스케줄러나 GitHub Actions에 같은 수집을 중복 등록하지 않는다.

`collector-runs/nas/dashboard.json`: 최근 화면 상태
`collector-runs/nas/current.log`: 현재/최근 로그
`collector-runs/nas/jobs/<jobId>/run.log`: 각 실행 로그
`collector-runs/nas/jobs/<jobId>/runs/<runId>/`: probe/full/status JSON

화면에는 로그 마지막 40KB를 표시한다. 실행 결과는 자동 삭제하지 않으므로 디스크 사용량을 관리한다. Docker 로그는 10MB×2개로 제한한다.

## 운영 명령

```sh
cd /volume1/docker/whoga/nas
docker compose logs --tail 100 collector
docker compose restart collector
docker compose down
```

GUI를 거치지 않고 검증하려면 관리 화면의 실행이 없는 상태에서:

```sh
docker compose run --rm --no-deps collector /app/nas/run.py probe --url https://fin.land.naver.com/complexes/140635
```

수동 CLI는 별도 출력 경로를 지정할 수 있다. CLI와 관리 화면 동시 실행은 피한다.

## 요구사항과 실패 처리

DS420+의 기본 메모리는 2GB다. 이 설정은 최대 메모리 1.5GB·CPU 1개로 제한하지만 DSM/다른 앱에 충분한 메모리가 남는지는 리소스 모니터로 확인해야 한다. 기본 2GB 환경의 실성능은 아직 검증하지 않았다.

- `ERR_CONNECTION_RESET`/Timeout: NAS에서도 네이버 접속 실패. 로그를 확보하고 원인 확인.
- sandbox/user namespace: NAS 커널과 Container Manager 호환성 확인. privileged나 샌드박드 해제로 자동 전환하지 않음.
- HTTP 401/403/404: GitHub 토큰·권한·브랜치 확인.
- HTTP 409/422: 같은 파일 존재 여부·브랜치 보호·쓰기 권한 확인.
- Docker exit 137: 메모리 부족 가능성 확인.

일반 사용자, 읽기전용 루트 파일시스템, cap_drop=ALL, no-new-privileges, Chromium 샌드박드를 사용한다. Playwright v1.63.0 seccomp 프로필에 사용자 네임스페이스 내부 chroot 허용을 추가했다. Docker 소켓·NAS 전체 공유폴더·호스트 네트워크는 연결하지 않는다.

## 검증 범위

로컬 검사: 표본→전체 단계, 로그인/요청 출처, 토큰 비노출, 중복 실행, 재시작 중단, 검증 파일 업로드 경로 확인.
CI: 실제 Docker 빌드와 샌드박드 브라우저, 로그인된 관리 화면, 설정 저장·즉시 브라우저 검사, 모바일 가로 넘침 검사.
**NAS 실제 접속·네이버 전체 수집·실제 PAT 업로드는 사용자의 NAS 설치 후 확인해야 한다.** CI의 GitHub 업로드 검사는 모의 응답으로 수행하며 실제 저장소에 수집 데이터를 쓰지 않는다.

출처:
- https://playwright.dev/python/docs/docker
- https://docs.github.com/en/rest/repos/contents#create-or-update-file-contents
- https://www.synology.com/dsm/packages/ContainerManager
- seccomp 원본: Microsoft Playwright v1.63.0, Apache-2.0 (LICENSE.playwright)
