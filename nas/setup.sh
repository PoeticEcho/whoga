#!/bin/sh
set -eu
cd "$(dirname "$0")"
umask 077
if [ "$(id -u)" = 0 ]; then
  echo "일반 NAS 계정으로 실행하세요. Docker 권한이 필요하면 아래 안내의 관리자 명령을 사용하세요." >&2
  exit 1
fi
if [ "$(uname -m)" != x86_64 ]; then
  echo '이 설치본은 DS420+ (x86_64) 전용입니다.' >&2
  exit 1
fi
mkdir -p ../collector-runs/nas ../nas-config
if [ ! -f .env ]; then
  dashboard_pass=$(od -An -N18 -tx1 /dev/urandom | tr -d ' \n')
  printf 'NAS_UID=%s\nNAS_GID=%s\nDASHBOARD_PASSWORD=%s\nNAS_BIND_IP=0.0.0.0\n' "$(id -u)" "$(id -g)" "$dashboard_pass" > .env
  echo '관리 계정: admin'
  echo "최초 관리 비밀번호: $dashboard_pass"
else
  echo '기존 .env를 유지합니다. 비밀번호는 .env에서 확인하세요.'
fi
chmod 600 .env
chmod 700 ../collector-runs/nas ../nas-config
if docker compose version >/dev/null 2>&1; then
  docker compose config --quiet
  docker compose up -d --build
elif command -v docker-compose >/dev/null 2>&1; then
  docker-compose config --quiet
  docker-compose up -d --build
else
  echo 'Container Manager 또는 Docker Compose 설치를 확인하세요.' >&2
  exit 1
fi
echo '설치 완료. http://NAS주소:8899 로 접속하세요.'
