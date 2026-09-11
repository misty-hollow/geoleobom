#!/usr/bin/env bash
# 충청권 OSRM foot 그래프 생성 (v2.3 부록 C).
#
#   Geofabrik south-korea pbf -> osmium extract(경계+버퍼) -> osrm-extract(foot)
#   -> osrm-partition -> osrm-customize
#
# 결과 *.osrm* 파일 세트는 저장소에 넣지 않는다(.gitignore). 서버에서 빌드하지 않고
# 여기서 만든 파일만 업로드한다(v2.3 4-1 "서버에서 빌드·전처리 금지").
#
# 사용법:  bash data/osrm/build_graph.sh [작업디렉터리]
# 기본 작업디렉터리는 data/osrm/build 이며 전부 gitignore된다.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work="${1:-$here/build}"
versions="$here/versions.json"

# docker는 PATH 우선, 없으면 Docker Desktop 사용자 설치 경로로 되돌아간다.
# 개인 경로를 하드코딩하지 않기 위해 LOCALAPPDATA를 쓴다.
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
# credential helper가 docker.exe와 같은 디렉터리에 있다. PATH에 없으면 pull이 실패한다.
PATH="$(dirname "$DOCKER"):$PATH"
export PATH

# Git Bash(MSYS)는 인자의 `/work` 같은 문자열을 Windows 경로로 바꿔 버린다. 컨테이너
# 안 경로가 깨지므로 변환을 끄고, 호스트 경로만 cygpath로 직접 바꾼다. Linux에서는
# cygpath가 없으므로 경로를 그대로 쓴다.
# docker 호출에만 붙인다. 전역으로 켜면 python 인자의 호스트 경로까지 안 바뀐다.
DOCKER_ENV=(env MSYS_NO_PATHCONV=1)
host_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    printf '%s\n' "$1"
  fi
}

read_version() {
  python -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8'))$2)" "$versions"
}

OSRM_IMAGE="$(read_version "$versions" "['osrm']['image']")"
OSRM_TAG="$(read_version "$versions" "['osrm']['tag']")"
OSRM_DIGEST="$(read_version "$versions" "['osrm']['digest']")"
OSRM_REF="${OSRM_IMAGE}:${OSRM_TAG}"

PBF_URL="https://download.geofabrik.de/asia/south-korea-latest.osm.pbf"
PBF="$work/south-korea-latest.osm.pbf"
EXTRACT="$work/chungcheong.osm.pbf"
POLY="$here/chungcheong.geojson"

mkdir -p "$work"

echo "== 1/5 OSRM 이미지 확인 =="
"${DOCKER_ENV[@]}" "$DOCKER" pull "$OSRM_REF" >/dev/null
actual_digest="$("${DOCKER_ENV[@]}" "$DOCKER" image inspect "$OSRM_REF" --format '{{index .RepoDigests 0}}' | cut -d@ -f2)"
if [ "$actual_digest" != "$OSRM_DIGEST" ]; then
  echo "이미지 digest가 versions.json과 다르다." >&2
  echo "  기대: $OSRM_DIGEST" >&2
  echo "  실제: $actual_digest" >&2
  exit 1
fi
echo "   $OSRM_REF @ $actual_digest"

echo "== 2/5 osmium 이미지 빌드 =="
"${DOCKER_ENV[@]}" "$DOCKER" build --quiet -f "$(host_path "$here/Dockerfile.osmium")" \
  -t geoleobom/osmium:local "$(host_path "$here")" >/dev/null
"${DOCKER_ENV[@]}" "$DOCKER" run --rm geoleobom/osmium:local --version | head -1

echo "== 3/5 south-korea pbf 내려받기 =="
if [ -f "$PBF" ]; then
  echo "   이미 있음: $PBF"
else
  curl -L --fail --progress-bar -o "$PBF" "$PBF_URL"
fi
ls -lh "$PBF" | awk '{print "   크기:", $5}'

echo "== 4/5 충청권 추출 (경계 + 버퍼) =="
"${DOCKER_ENV[@]}" "$DOCKER" run --rm -v "$(host_path "$work"):/work" -v "$(host_path "$here"):/cfg:ro" \
  geoleobom/osmium:local \
  extract --polygon /cfg/chungcheong.geojson --overwrite \
  --output /work/chungcheong.osm.pbf /work/south-korea-latest.osm.pbf
ls -lh "$EXTRACT" | awk '{print "   추출 크기:", $5}'

echo "== 5/5 OSRM foot MLD 전처리 =="
run_osrm() {
  "${DOCKER_ENV[@]}" "$DOCKER" run --rm -v "$(host_path "$work"):/work" "$OSRM_REF" "$@"
}
run_osrm osrm-extract -p /opt/foot.lua /work/chungcheong.osm.pbf
run_osrm osrm-partition /work/chungcheong.osrm
run_osrm osrm-customize /work/chungcheong.osrm

echo
echo "완료. 결과 파일:"
ls -1 "$work"/chungcheong.osrm* | sed 's/^/   /'
echo
echo "기동:  bash data/osrm/run_osrm.sh $work"
