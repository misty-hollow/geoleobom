#!/usr/bin/env bash
# 롤백 (AGENTS.md 5절).
#
# "직전 정상 이미지·설정으로 복구하고 실제 응답을 확인한다. 데이터 삭제나
#  비호환 역변환은 일반 코드 롤백으로 취급하지 않는다."
#
#   bash deploy/rollback.sh code   — .env.previous의 이미지로 되돌린다
#   bash deploy/rollback.sh data   — /srv/geoleobom/data/previous 버전으로 되돌린다
#
# 되돌린 뒤 반드시 deploy/smoke.py로 실제 응답을 확인한다. 이 스크립트는 확인하지 않는다.
# 데이터 롤백은 **삭제하지 않는다.** current 링크만 옮기므로 다시 앞으로 갈 수 있다.

set -euo pipefail

HOST="geoleobom"
REMOTE_DIR="/opt/geoleobom"
DATA_ROOT="/srv/geoleobom/data"

MODE="${1:-}"
shift || true
while [[ $# -gt 0 ]]; do
	case "$1" in
	--host)
		HOST="${2:?}"
		shift 2
		;;
	*)
		echo "usage: $0 <code|data> [--host <ssh-host>]" >&2
		exit 2
		;;
	esac
done

case "$MODE" in
code)
	ssh "$HOST" "bash -s" <<REMOTE
set -euo pipefail
cd "$REMOTE_DIR"
test -f .env.previous || { echo ".env.previous가 없다. 되돌릴 직전 설정이 없다."; exit 1; }

PREV_IMAGE="\$(grep '^GEOLEOBOM_API_IMAGE=' .env.previous | cut -d= -f2-)"
test -n "\$PREV_IMAGE" || { echo ".env.previous에 이미지 값이 없다."; exit 1; }
echo "되돌릴 이미지: \$PREV_IMAGE"

cp .env .env.rolled-back-from
grep -v '^GEOLEOBOM_API_IMAGE=' .env > .env.next || true
echo "GEOLEOBOM_API_IMAGE=\$PREV_IMAGE" >> .env.next
mv .env.next .env
chmod 600 .env

docker compose -f compose.yaml pull api
docker compose -f compose.yaml up -d api
RUNNING="\$(docker inspect geoleobom-api --format '{{.Image}}')"
WANTED="\$(docker image inspect "\$PREV_IMAGE" --format '{{.Id}}')"
test "\$RUNNING" = "\$WANTED" || { echo "되돌린 이미지가 실제로 돌고 있지 않다"; exit 1; }
echo "코드 롤백 완료. image id: \$RUNNING"
REMOTE
	;;
data)
	ssh "$HOST" "bash -s" <<REMOTE
set -euo pipefail
cd "$REMOTE_DIR"
test -L "$DATA_ROOT/previous" || { echo "previous 링크가 없다. 되돌릴 직전 데이터가 없다."; exit 1; }

PREV="\$(readlink "$DATA_ROOT/previous")"
CURR="\$(readlink "$DATA_ROOT/current")"
echo "current=\$CURR -> previous=\$PREV 로 되돌린다"

# --- 사전조건은 서비스를 건드리기 **전에** 전부 확인한다 ---
# 정지·링크 교체 뒤에 검사하면, 검사가 실패했을 때 서비스는 내려간 채 current와
# .env가 어긋난 상태로 남는다. 되돌리는 도중에 더 나쁜 상태를 만들지 않는다.
test -f "$DATA_ROOT/\$PREV/poi.gpkg" || { echo "직전 버전 데이터가 온전하지 않다"; exit 1; }
test "\$PREV" != "\$CURR" || { echo "previous와 current가 같은 버전이다. 되돌릴 곳이 없다."; exit 1; }
# 기준일은 버전 디렉터리가 들고 있다. 데이터와 기준일을 항상 짝지어 되돌린다.
PREV_POI_DATE="\$(cat "$DATA_ROOT/\$PREV/poi_date.txt" 2>/dev/null || true)"
test -n "\$PREV_POI_DATE" || { echo "직전 버전에 poi_date.txt가 없다. 기준일을 알 수 없어 멈춘다."; exit 1; }

docker compose -f compose.yaml stop api osrm
# 링크만 맞바꾼다. 어느 쪽도 지우지 않으므로 다시 앞으로 갈 수 있다.
ln -sfn "\$CURR" "$DATA_ROOT/previous"
ln -sfn "\$PREV" "$DATA_ROOT/current"

grep -v -e '^GEOLEOBOM_DATA_VERSION=' -e '^GEOLEOBOM_POI_DATE=' .env > .env.next || true
echo "GEOLEOBOM_DATA_VERSION=\$PREV" >> .env.next
echo "GEOLEOBOM_POI_DATE=\$PREV_POI_DATE" >> .env.next
mv .env.next .env
chmod 600 .env
echo "되돌린 기준일: \$PREV_POI_DATE"

docker compose -f compose.yaml up -d --force-recreate api osrm
ls -l "$DATA_ROOT/current" "$DATA_ROOT/previous"
REMOTE
	;;
*)
	echo "usage: $0 <code|data> [--host <ssh-host>]" >&2
	exit 2
	;;
esac

echo
echo "되돌렸다. 실제 응답을 확인하기 전에는 복구됐다고 하지 않는다:"
echo "  python deploy/smoke.py --base-url https://geoleobom.kr"
