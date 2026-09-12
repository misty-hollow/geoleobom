#!/usr/bin/env bash
# 롤백 (AGENTS.md 5절).
#
# "직전 정상 이미지·설정으로 복구하고 실제 응답을 확인한다. 데이터 삭제나
#  비호환 역변환은 일반 코드 롤백으로 취급하지 않는다."
#
#   bash deploy/rollback.sh code   — 마지막으로 **스모크를 통과한** 이미지 + 그 커밋의 설정
#   bash deploy/rollback.sh data   — /srv/geoleobom/data/previous 버전으로 되돌린다
#   bash deploy/rollback.sh web    — /srv/geoleobom/web/previous 빌드로 되돌린다
#
# 셋은 **서로 다른 산출물**이라 따로 되돌린다. 웹만 깨졌는데 API 컨테이너까지 재생성할
# 이유가 없고, 반대로 API를 되돌릴 때 화면까지 함께 움직이면 무엇을 되돌렸는지 말할 수 없다.
#
# 되돌린 뒤 반드시 deploy/smoke.py로 실제 응답을 확인한다. 이 스크립트는 확인하지 않는다.
# 데이터 롤백은 **삭제하지 않는다.** current 링크만 옮기므로 다시 앞으로 갈 수 있다.
#
# ## 이미지와 설정을 함께 되돌린다
#
# 예전에는 `.env`의 이미지 줄만 바꿨다. 그러면 **옛 이미지가 새 compose.yaml·
# Caddyfile로 돈다.** 그 조합은 어디서도 검사된 적이 없다 — 새 설정이 새 이미지에만
# 있는 환경변수나 마운트를 기대할 수 있고, 되돌린 것이 무엇인지도 말할 수 없다.
#
# 그래서 `.env.last-good`에 이미지와 **그 배포의 커밋 SHA**를 함께 적어 두고,
# 롤백은 그 커밋의 `deploy/`를 다시 올린 뒤 이미지를 되돌린다.
#
# ## 정상 복구 지점의 의미
#
# `.env.last-good`은 **스모크를 통과한** 설정이다(deploy_api.sh가 통과 뒤에만 쓴다).
# `.env.before-this-deploy`는 그냥 "직전에 무엇이 돌았나"라서 복구 기준이 아니다 —
# 깨진 배포를 두 번 하면 그 파일은 깨진 쪽을 가리킨다.

set -euo pipefail

HOST="geoleobom"
REMOTE_DIR="/opt/geoleobom"
DATA_ROOT="/srv/geoleobom/data"
WEB_ROOT="/srv/geoleobom/web"
BASE_URL="https://geoleobom.kr"
READY_TIMEOUT_S=90

MODE="${1:-}"
shift || true
while [[ $# -gt 0 ]]; do
	case "$1" in
	--host)
		HOST="${2:?}"
		shift 2
		;;
	*)
		echo "usage: $0 <code|data|web> [--host <ssh-host>]" >&2
		exit 2
		;;
	esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$MODE" in
code)
	echo "== 1. 정상 복구 지점 읽기"
	LAST_GOOD="$(ssh "$HOST" "bash -s" <<'READ'
set -euo pipefail
cd /opt/geoleobom
if [[ -f .env.last-good ]]; then
	echo "source=last-good"
	grep -E '^(GEOLEOBOM_API_IMAGE|GEOLEOBOM_DEPLOYED_SHA)=' .env.last-good || true
elif [[ -f .env.previous ]]; then
	# 이전 방식으로 남은 파일. 스모크 통과 여부가 기록돼 있지 않다.
	echo "source=previous"
	grep -E '^(GEOLEOBOM_API_IMAGE|GEOLEOBOM_DEPLOYED_SHA)=' .env.previous || true
else
	echo "source=none"
fi
READ
	)"

	SOURCE="$(echo "$LAST_GOOD" | grep '^source=' | cut -d= -f2)"
	PREV_IMAGE="$(echo "$LAST_GOOD" | grep '^GEOLEOBOM_API_IMAGE=' | cut -d= -f2- || true)"
	PREV_SHA="$(echo "$LAST_GOOD" | grep '^GEOLEOBOM_DEPLOYED_SHA=' | cut -d= -f2- || true)"

	if [[ "$SOURCE" == "none" || -z "$PREV_IMAGE" ]]; then
		echo "되돌릴 정상 복구 지점이 없다 (.env.last-good 도 .env.previous 도 쓸 수 없다)." >&2
		echo "스모크를 통과한 배포가 아직 없다는 뜻이다." >&2
		exit 1
	fi
	echo "   출처: $SOURCE"
	echo "   이미지: $PREV_IMAGE"
	if [[ "$SOURCE" == "previous" ]]; then
		echo "   주의: 이전 방식의 .env.previous다. **스모크 통과 기록이 아니다.**" >&2
	fi

	echo "== 2. 그 커밋의 배포 설정 복원"
	if [[ -z "$PREV_SHA" ]]; then
		echo "   복구 지점에 커밋 SHA가 없다 — 설정은 지금 서버에 있는 것을 그대로 쓴다." >&2
		echo "   **이미지와 설정의 짝이 보장되지 않는다.** 되돌린 뒤 특히 주의해서 확인해라." >&2
	elif ! git -C "$REPO_ROOT" cat-file -e "$PREV_SHA^{commit}" 2>/dev/null; then
		echo "   커밋 $PREV_SHA 가 로컬에 없다 (git fetch 했는가). 설정을 되돌리지 못한다." >&2
		exit 1
	else
		STAGE_DIR="$(mktemp -d)"
		trap 'rm -rf "$STAGE_DIR"' EXIT
		git -C "$REPO_ROOT" archive "$PREV_SHA" deploy | tar -x -C "$STAGE_DIR"
		scp -q "$STAGE_DIR/deploy/compose.yaml" "$STAGE_DIR/deploy/Caddyfile" "$HOST:$REMOTE_DIR/"
		echo "   커밋 $PREV_SHA 의 deploy/ 복원 (웹 배포물은 별도다 — rollback.sh web)"
	fi

	echo "== 3. 이미지 되돌리고 기동"
	ssh "$HOST" "bash -s" <<REMOTE
set -euo pipefail
cd "$REMOTE_DIR"

# 되돌리기 직전 상태를 남긴다. 롤백 자체가 잘못됐을 때 볼 곳이 필요하다.
cp .env .env.rolled-back-from

grep -v -e '^GEOLEOBOM_API_IMAGE=' -e '^GEOLEOBOM_DEPLOYED_SHA=' .env > .env.next || true
echo "GEOLEOBOM_API_IMAGE=$PREV_IMAGE" >> .env.next
if [[ -n "$PREV_SHA" ]]; then
	echo "GEOLEOBOM_DEPLOYED_SHA=$PREV_SHA" >> .env.next
fi
mv .env.next .env
chmod 600 .env

docker pull --quiet "$PREV_IMAGE" >/dev/null
# **서비스를 지정하지 않는다.** 위에서 그 커밋의 compose.yaml을 통째로 복원했으므로,
# api만 재생성하면 osrm·caddy의 서비스 정의 변경(이미지 태그·명령·마운트)이 반영되지
# 않아 "설정은 옛 커밋 것인데 돌고 있는 컨테이너는 새 정의"인 상태가 남는다.
# 인자 없는 up -d는 **정의가 바뀐 것만** 재생성하므로 필요 이상으로 끊지도 않는다.
docker compose -f compose.yaml up -d --force-recreate api
docker compose -f compose.yaml up -d

echo "   API 응답 대기 (최대 ${READY_TIMEOUT_S}s)"
deadline=\$(( \$(date +%s) + $READY_TIMEOUT_S ))
ready=0
while [[ \$(date +%s) -lt \$deadline ]]; do
	if docker exec geoleobom-api python -c "
import sys, urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
		ready=1
		break
	fi
	state="\$(docker inspect geoleobom-api --format '{{.State.Status}}' 2>/dev/null || echo missing)"
	if [[ "\$state" == "exited" || "\$state" == "dead" || "\$state" == "missing" ]]; then
		echo "   api 컨테이너 상태: \$state" >&2
		break
	fi
	sleep 2
done
if [[ \$ready -ne 1 ]]; then
	echo "되돌린 이미지가 응답하지 않는다. 최근 로그:" >&2
	docker logs --tail 40 geoleobom-api 2>&1 >&2 || true
	exit 1
fi

RUNNING="\$(docker inspect geoleobom-api --format '{{.Image}}')"
WANTED="\$(docker image inspect "$PREV_IMAGE" --format '{{.Id}}')"
test "\$RUNNING" = "\$WANTED" || { echo "되돌린 이미지가 실제로 돌고 있지 않다"; exit 1; }

# 설정을 되돌렸으면 Caddy도 다시 읽혀야 한다. 바인드 마운트라 재생성되지 않는다.
if docker exec geoleobom-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
	echo "Caddy 설정 재적용 완료"
else
	echo "Caddy 설정 재적용 실패 — 돌던 설정이 유지된다." >&2
	exit 1
fi
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
test -s "$DATA_ROOT/\$PREV/poi.gpkg" || { echo "직전 버전 데이터가 온전하지 않다"; exit 1; }
test -s "$DATA_ROOT/\$PREV/osrm/chungcheong.osrm.fileIndex" || {
	echo "직전 버전에 OSRM 파일 세트가 없다. 데이터와 보행망은 같은 묶음이어야 한다."
	exit 1
}
test "\$PREV" != "\$CURR" || { echo "previous와 current가 같은 버전이다. 되돌릴 곳이 없다."; exit 1; }
# 기준일은 버전 디렉터리가 들고 있다. 데이터와 기준일을 항상 짝지어 되돌린다.
PREV_POI_DATE="\$(cat "$DATA_ROOT/\$PREV/poi_date.txt" 2>/dev/null || true)"
test -n "\$PREV_POI_DATE" || { echo "직전 버전에 poi_date.txt가 없다. 기준일을 알 수 없어 멈춘다."; exit 1; }

# 묶음이 손대진 않았는지. MANIFEST가 있으면 대조한다.
if [[ -f "$DATA_ROOT/\$PREV/MANIFEST" ]]; then
	want_sha="\$(grep '^poi_gpkg_sha256=' "$DATA_ROOT/\$PREV/MANIFEST" | cut -d= -f2-)"
	have_sha="\$(sha256sum "$DATA_ROOT/\$PREV/poi.gpkg" | cut -d' ' -f1)"
	test "\$want_sha" = "\$have_sha" || {
		echo "직전 버전의 poi.gpkg가 MANIFEST와 다르다. 되돌리지 않는다."
		exit 1
	}
	want_date="\$(grep '^poi_date=' "$DATA_ROOT/\$PREV/MANIFEST" | cut -d= -f2-)"
	test "\$want_date" = "\$PREV_POI_DATE" || {
		echo "직전 버전의 poi_date가 MANIFEST와 다르다: \$want_date != \$PREV_POI_DATE"
		exit 1
	}
	echo "   MANIFEST 대조 통과"
fi

# **정지 실패를 무시하지 않는다.**
if ! docker compose -f compose.yaml stop api osrm; then
	echo "api·osrm 정지에 실패했다. 참조를 바꾸지 않고 멈춘다." >&2
	exit 1
fi

# 링크만 맞바꾼다. 어느 쪽도 지우지 않으므로 다시 앞으로 갈 수 있다.
ln -sfn "\$CURR" "$DATA_ROOT/previous"
ln -sfn "\$PREV" "$DATA_ROOT/current"

grep -v -e '^GEOLEOBOM_DATA_VERSION=' -e '^GEOLEOBOM_POI_DATE=' .env > .env.next || true
echo "GEOLEOBOM_DATA_VERSION=\$PREV" >> .env.next
echo "GEOLEOBOM_POI_DATE=\$PREV_POI_DATE" >> .env.next
mv .env.next .env
chmod 600 .env
echo "되돌린 기준일: \$PREV_POI_DATE"

# deploy_data.sh와 같은 가드. 이미지를 한 번도 배포하지 않았으면 api를 올리지
# 않는다. compose 기본값은 레지스트리에 없는 태그라 pull에서 실패하고, 그러면
# 데이터는 이미 되돌아갔는데 롤백이 실패한 것처럼 보인다.
if grep -q '^GEOLEOBOM_API_IMAGE=' .env; then
	docker compose -f compose.yaml up -d --force-recreate api osrm

	echo "   API 응답 대기 (최대 ${READY_TIMEOUT_S}s)"
	deadline=\$(( \$(date +%s) + $READY_TIMEOUT_S ))
	ready=0
	while [[ \$(date +%s) -lt \$deadline ]]; do
		got="\$(docker exec geoleobom-api python -c "
import json, urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2) as r:
        print(json.load(r).get('data_version') or '')
except Exception:
    pass
" 2>/dev/null || true)"
		if [[ "\$got" == "\$PREV" ]]; then
			ready=1
			break
		fi
		state="\$(docker inspect geoleobom-api --format '{{.State.Status}}' 2>/dev/null || echo missing)"
		if [[ "\$state" == "exited" || "\$state" == "dead" || "\$state" == "missing" ]]; then
			echo "   api 컨테이너 상태: \$state" >&2
			break
		fi
		sleep 2
	done
	if [[ \$ready -ne 1 ]]; then
		echo "되돌린 데이터로 API가 응답하지 않는다. 최근 로그:" >&2
		docker logs --tail 40 geoleobom-api 2>&1 >&2 || true
		exit 1
	fi
	echo "   /api/health data_version = \$PREV"
else
	echo "   GEOLEOBOM_API_IMAGE가 없다 — osrm만 올린다."
	docker compose -f compose.yaml up -d --force-recreate osrm
fi
ls -l "$DATA_ROOT/current" "$DATA_ROOT/previous"
REMOTE
	;;
web)
	# 웹은 버전 디렉터리 + 심볼릭 링크라 **링크만 맞바꾼다.** 어느 쪽도 지우지 않으므로
	# 다시 앞으로 갈 수 있다(데이터 롤백과 같은 방식).
	ssh "$HOST" "bash -s" <<REMOTE
set -euo pipefail
cd "$WEB_ROOT"
test -L previous || { echo "previous 링크가 없다. 되돌릴 직전 빌드가 없다."; exit 1; }

PREV="\$(readlink previous)"
CURR="\$(readlink current)"
test "\$PREV" != "\$CURR" || { echo "previous와 current가 같다. 되돌릴 곳이 없다."; exit 1; }
test -f "\$PREV/index.html" || { echo "직전 빌드가 온전하지 않다: \$PREV"; exit 1; }

echo "current=\$CURR -> previous=\$PREV 로 되돌린다"
ln -sfn "\$CURR" previous
ln -sfn "\$PREV" current
ls -l current previous
REMOTE
	echo
	echo "웹을 되돌렸다. 실제 응답을 확인하기 전에는 복구됐다고 하지 않는다:"
	echo "  python deploy/smoke.py --base-url $BASE_URL --pages-only"
	exit 0
	;;
*)
	echo "usage: $0 <code|data|web> [--host <ssh-host>]" >&2
	exit 2
	;;
esac

echo
echo "되돌렸다. 실제 응답을 확인하기 전에는 복구됐다고 하지 않는다:"
echo "  python deploy/smoke.py --base-url https://geoleobom.kr"
