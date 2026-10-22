#!/bin/sh
set -eu

cd /volume2/docker/whoga/nas

STAMP=$(date +%Y%m%d_%H%M%S)

echo "=== Whoga DS420+ 호환성 수정 ==="

for FILE in compose.yaml compose.bind.yaml
do
    if [ ! -f "$FILE" ]; then
        echo "파일 없음: $FILE"
        continue
    fi

    # 원본 백업
    cp -p "$FILE" "$FILE.bak.$STAMP"

    # NAS 커널에서 지원하지 않는 제한만 제거
    sed -i \
      -e '/^[[:space:]]*cpus:[[:space:]]*/d' \
      -e '/^[[:space:]]*pids_limit:[[:space:]]*/d' \
      -e '/^[[:space:]]*-[[:space:]]*seccomp=/d' \
      "$FILE"

    echo "수정 완료: $FILE"
done

echo ""
echo "=== 보안 설정 확인 ==="
grep -nE 'mem_limit|cap_drop|security_opt|no-new-privileges|seccomp|pids_limit|cpus:' \
  compose.yaml compose.bind.yaml || true

echo ""
echo "=== Compose 설정 검사 ==="
docker compose -f compose.yaml config --quiet
docker compose -f compose.bind.yaml config --quiet

echo "설정 검사 통과"
echo "원본 백업 시간: $STAMP"
