#!/usr/bin/env bash
# 로컬 OSRM 기동 (v2.3 4-1, 부록 C).
#
#   osrm-routed --algorithm mld --max-table-size 200
#
# 개발용이라 127.0.0.1:5000에만 묶는다. 운영에서는 compose가 내부 네트워크로만
# 노출하며 ports: 매핑을 만들지 않는다(v2.3 5절).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work="${1:-$here/build}"
port="${2:-5000}"
versions="$here/versions.json"

find_docker() {
  if command -v docker >/dev/null 2>&1; then
    command -v docker
    return
  fi
  local fallback="${LOCALAPPDATA:-}/Programs/DockerDesktop/resources/bin/docker.exe"
  if [ -x "$fallback" ]; then
    printf '%s\n' "$fallback"
    return
  fi
  echo "docker를 찾지 못했다. PATH에 넣거나 Docker Desktop을 실행해라." >&2
  exit 1
}

DOCKER="$(find_docker)"
PATH="$(dirname "$DOCKER"):$PATH"
export PATH

# Git Bash가 컨테이너 안 경로를 Windows 경로로 바꾸지 않게 한다(build_graph.sh와 동일).
# docker 호출에만 붙인다. 전역으로 켜면 python 인자의 호스트 경로까지 안 바뀐다.
DOCKER_ENV=(env MSYS_NO_PATHCONV=1)
host_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    printf '%s\n' "$1"
  fi
}

OSRM_REF="$(python -c "
import json,sys
v = json.load(open(sys.argv[1], encoding='utf-8'))['osrm']
print(f\"{v['image']}:{v['tag']}\")
" "$versions")"

if [ ! -f "$work/chungcheong.osrm.mldgr" ]; then
  echo "그래프가 없다: $work. 먼저 build_graph.sh를 실행해라." >&2
  exit 1
fi

echo "OSRM 기동: $OSRM_REF  http://127.0.0.1:$port"
exec "${DOCKER_ENV[@]}" "$DOCKER" run --rm --name geoleobom-osrm-dev \
  -p "127.0.0.1:$port:5000" -v "$(host_path "$work"):/work" "$OSRM_REF" \
  osrm-routed --algorithm mld --max-table-size 200 /work/chungcheong.osrm
