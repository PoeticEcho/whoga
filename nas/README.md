# WhoGa · Synology NAS Docker 검증판

대상: DS420+ / x86_64 / DSM Container Manager(Docker Compose).
DS420j 등 ARM 모델은 이 amd64 구성의 적용 대상이 아니다. DSM 제어판 → 정보 센터의 정확한 모델명, 메모리, DSM 버전을 먼저 확인한다. Container Manager의 모델 지원 여부와 이 이미지의 CPU 호환성은 별개다.

## 이번 버전이 하는 일

NAS 인터넷 회선에서 https://fin.land.naver.com/complexes/140635 에 접속하여 매매 필터와 단지번호를 확인한다.
- smoke: 외부 접속 없이 Chromium 샌드박드 기동 확인
- probe: 처음 3개 카드 및 묶음 매물 확인
- full: 같은 실행에서 probe 성공 후 전체 목록 수집·수량/매물번호 검증

기존 첨부본 collector.py를 그대로 호출한다. 가상화 목록의 두 차례 전수 관측은 아직 포함하지 않으며, WhoGa 운영 스키마 변환·Pages 발행은 별도다. 결과에는 publicationEligible=false를 기록한다. NAS 실접속 성공을 아직 확인하지 않았으므로 정기 운영 활성화 전 단계다.

## 설치

1. 패키지 센터에서 Container Manager 설치. DS420+ 기본 메모리 2GB에서 DSM/다른 앱의 여유 메모리를 확인한다. 컨테이너 최대 1.5GB, CPU 1개로 제한했지만 이것이 DSM의 여유 메모리를 보장하지는 않는다.
2. GitHub `map-collector-v2` 브랜치를 ZIP으로 내려받아 NAS의 `/volume1/docker/whoga`에 압축 해제한다. 해당 폴더 바로 아래 `nas`와 `experiments`가 있어야 한다.
3. NAS 터미널에서 아래 실행. NAS 접근 권한이 있는 로컬 계정으로 수행하며, `id`는 수집 폴더를 소유할 계정 기준이다. 관리자 Docker 권한이 필요한 환경에서는 Docker 명령에만 `sudo`를 붙인다.

```sh
cd /volume1/docker/whoga
mkdir -p collector-runs/nas
printf 'NAS_UID=%s\nNAS_GID=%s\n' "$(id -u)" "$(id -g)" > nas/.env
chmod 700 collector-runs/nas
cd nas
docker compose build collector
docker compose run --rm collector smoke
docker compose run --rm collector probe
```

Compose 구버전이면 `docker-compose` 명령을 사용한다. 프로젝트 UI를 이용하는 경우 프로젝트 경로는 `nas`, Compose 파일은 `nas/compose.yaml`이다. 폴더 권한 오류 시 실제 NAS_UID/NAS_GID와 대상 폴더 소유권/DSM ACL을 확인한다. 전체 공유폴더 권한을 개방하지 않는다.

`probe-passed`를 확인한 후:

```sh
docker compose run --rm collector full
```

full 명령도 probe부터 다시 실행한다. `restart: no`이므로 실행 후 컨테이너가 종료되는 것이 정상이다.

## 결과와 실패 판단

`collector-runs/nas/status.json`에 최근 실행 상태, `runs/<runId>/`에 이번 실행의 probe.json/full.json/status.json을 저장한다. 이전 실행 파일은 유지한다. 실패 시 종료코드 1, 동시 실행은 2. 프로세스가 강제 종료되면 종료 상태 기록이 없을 수 있으므로 오래된 status.json을 새 실행의 성공으로 해석하지 않는다.

- browser-ready: Docker 브라우저 기동만 확인됨; 네이버 수집 성공 아님.
- probe-passed: 표본 검사만 성공.
- full-passed: 이번 전체 목록의 수량·식별자 검사 성공. 운영 발행 완료 아님.
- ERR_CONNECTION_RESET/Timeout: NAS 회선에서도 접속 실패. 원인을 추가 확인해야 하며 자동 반복하지 않는다.
- sandbox/user namespace 오류: NAS 커널과 Container Manager 호환성 확인 필요. privileged/SYS_ADMIN/샌드박드 해제로 자동 전환하지 않는다.
- 메모리 부족/OOM: 리소스 모니터와 컨테이너 종료코드를 확인한다.

브라우저 샌드박드를 명시적으로 켠다. Playwright 공식 v1.63.0 seccomp 프로필에 샌드박드 내부의 chroot 호출 허용을 추가했다. 호스트 capability는 모두 제거한 상태를 유지한다. 외부 공개 포트, 호스트 네트워크, Docker 소켓 마운트, GitHub 토큰은 사용하지 않는다.

## GitHub Actions 연결 단계

이 컨테이너는 수집기다. GitHub runner 등록은 포함하지 않는다. 먼저 NAS에서 smoke/probe/full 결과를 확인한다. 이후 승인된 전용 실행 환경에 self-hosted runner를 등록하여 위 동일 명령을 실행하고 결과를 artifact로 전달할 수 있다. 이는 `github-hosted`에서 `self-hosted`로 바뀌는 구성이다.

공개 저장소의 임의 PR 코드를 개인 NAS에서 실행하는 runner를 만들지 않는다. 전용 비공개 제어 저장소, 고정된 검토 코드, 격리된 실행 계정을 기준으로 별도 연결한다. Docker만으로 임의 runner 코드와 NAS 전체가 격리된다고 간주하지 않는다.

9시 정기 실행 및 GitHub 자동 발행은 아직 추가하지 않았다. NAS 수집의 완전성·기존 앱 스키마 변환·발행 검증을 마친 뒤 연결한다.

## 검증과 출처

로컬: probe→full 게이트 검사 3개 통과. 현재 개발 환경에는 Docker 데몬이 없어 NAS와 동일한 실행 검증은 할 수 없다. 별도 Actions `nas Docker build and smoke`는 이미지 빌드/일반 Linux 브라우저 기동만 검사하며 NAS 접속 증명이 아니다.

- https://playwright.dev/python/docs/docker
- https://github.com/microsoft/playwright/blob/v1.63.0/utils/docker/seccomp_profile.json
- https://www.synology.com/dsm/packages/ContainerManager
- DS420+ 공식 데이터시트: Intel Celeron J4025, 기본 2GB DDR4, 최대 6GB

seccomp_profile.json 출처: Microsoft Playwright v1.63.0 (Apache-2.0); LICENSE.playwright 참조.
