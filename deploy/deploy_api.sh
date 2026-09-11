#!/usr/bin/env bash
# 코드 배포: GHCR 이미지를 커밋 SHA 태그 + digest로 고정해 서버에 반영한다.
#
# 기준: v2.3 4-1(서버에서 빌드하지 않는다), 5절(서버 구성), AGENTS.md 5절.
# **데이터 교체와 분리한다.** 데이터는 deploy/deploy_data.sh가 담당한다.
#
# 사용법 (개발 PC에서):
#   bash deploy/deploy_api.sh <커밋 SHA>
#   bash deploy/deploy_api.sh <커밋 SHA> --host geoleobom
#   bash deploy/deploy_api.sh <커밋 SHA> --skip-smoke     # 스모크를 따로 돌릴 때만
#
# 하는 일:
#   1. 레지스트리에서 그 태그의 digest를 조회한다(태그만 믿지 않는다).
#   2. **그 커밋의** deploy/ 설정을 서버 /opt/geoleobom에 복사한다.
#   3. 태그 + digest를 .env에 적고 up -d 한다.
#   4. **API가 실제로 응답할 때까지 기다린다** (제한시간 있음).
#   5. 실행 중인 digest를 대조하고 Caddy 설정을 재적용한다.
#   6. 스모크를 돌리고, **통과한 뒤에만** 정상 복구 지점(.env.last-good)을 갱신한다.
#
# ## up -d 성공은 기동 성공이 아니다
#
# `docker compose up -d`는 컨테이너를 **만들었다**는 뜻이지 앱이 요청을 받는다는
# 뜻이 아니다. 예전에는 up -d 직후 digest만 대조하고 "기동까지 확인했다"고 적었다.
# 실제로는 그 사이에 죽는 경우가 있었다(httpx가 dev 의존성이라 ModuleNotFoundError).
# 그래서 `/api/health`가 답할 때까지 기다린 다음에 다음 단계로 간다.
#
# ## 정상 복구 지점은 스모크 통과 뒤에만 움직인다
#
# 예전에는 배포를 시작하면서 직전 `.env`를 `.env.previous`로 복사했다. 그러면
# **깨진 배포를 두 번 연속 하면** 복구 지점이 깨진 쪽을 가리킨다. 이제 스모크가
# 통과한 설정만 `.env.last-good`이 되고, 롤백은 그 파일만 본다.
#
# ## 설정과 이미지는 함께 되돌아간다
#
# `.env`에 배포한 커밋 SHA를 함께 적는다. compose.yaml·Caddyfile은 그 커밋의 것이므로,
# 롤백이 **옛 이미지에 새 설정을 섞지 않고** 둘을 함께 되돌릴 수 있다.

set -euo pipefail

HOST="geoleobom"
REMOTE_DIR="/opt/geoleobom"
IMAGE_REPO="ghcr.io/misty-hollow/geoleobom-api"
BASE_URL="https://geoleobom.kr"
SKIP_SMOKE=0
# API가 응답하기까지 기다리는 한계. 넘으면 실패로 끝낸다(무한정 기다리지 않는다).
READY_TIMEOUT_S=90

usage() {
	echo "usage: $0 <commit-sha> [--host <ssh-host>] [--base-url <url>] [--skip-smoke]" >&2
	exit 2
}

[[ $# -ge 1 ]] || usage
COMMIT_SHA="$1"
shift
while [[ $# -gt 0 ]]; do
	case "$1" in
	--host)
		HOST="${2:?--host needs a value}"
		shift 2
		;;
	--base-url)
		BASE_URL="${2:?--base-url needs a value}"
		shift 2
		;;
	--skip-smoke)
		SKIP_SMOKE=1
		shift
		;;
	*) usage ;;
	esac
done

if [[ ! "$COMMIT_SHA" =~ ^[0-9a-f]{40}$ ]]; then
	echo "커밋 SHA 40자를 그대로 넣는다(브랜치 이름·latest 금지): $COMMIT_SHA" >&2
	exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 설정은 **배포하는 커밋의 것**이어야 한다. 작업 트리의 수정본을 올리면 서버 설정이
# 어느 커밋의 것인지 알 수 없게 되고, 롤백이 짝을 찾지 못한다.
if ! git -C "$REPO_ROOT" cat-file -e "$COMMIT_SHA^{commit}" 2>/dev/null; then
	echo "그 커밋이 로컬에 없다: $COMMIT_SHA (git fetch 했는가)" >&2
	exit 2
fi

STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT
git -C "$REPO_ROOT" archive "$COMMIT_SHA" deploy | tar -x -C "$STAGE_DIR"
for required in deploy/compose.yaml deploy/Caddyfile; do
	[[ -f "$STAGE_DIR/$required" ]] || {
		echo "그 커밋에 $required 가 없다" >&2
		exit 1
	}
done

echo "== 1. 레지스트리에서 digest 조회 ($IMAGE_REPO:$COMMIT_SHA)"
# 태그는 옮겨질 수 있으므로 배포 시점의 digest를 고정해 그 값으로 실행한다.
#
# `docker image inspect`의 RepoDigests[0]을 쓰지 않는다. 같은 image id가 여러 digest로
# 알려져 있으면(같은 태그를 다른 manifest로 덮어쓴 뒤 등) 0번이 방금 pull한 태그의
# digest라는 보장이 없다. imagetools는 레지스트리에 **태그를 직접 물어** 답을 준다.
DIGEST="$(ssh "$HOST" "docker buildx imagetools inspect '$IMAGE_REPO:$COMMIT_SHA' --format '{{.Manifest.Digest}}'" | tr -d '\r\n')"

if [[ ! "$DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]; then
	echo "digest를 얻지 못했다: '$DIGEST'" >&2
	exit 1
fi
PINNED="$IMAGE_REPO:$COMMIT_SHA@$DIGEST"
echo "   $PINNED"

# digest로 pull한다. 태그로 받아 온 것이 아니라 이 바이트를 받았음을 확실히 한다.
ssh "$HOST" "docker pull --quiet '$PINNED'" >/dev/null

echo "== 2. 배포 설정 복사 (커밋 $COMMIT_SHA 의 deploy/)"
scp -q "$STAGE_DIR/deploy/compose.yaml" "$STAGE_DIR/deploy/Caddyfile" "$HOST:$REMOTE_DIR/"
scp -q -r "$STAGE_DIR/deploy/site" "$HOST:$REMOTE_DIR/"

echo "== 3~5. .env 갱신 → up -d → 응답 대기 → digest 확인 → Caddy 재적용"
ssh "$HOST" "bash -s" <<REMOTE
set -euo pipefail
cd "$REMOTE_DIR"

# 되돌릴 때 쓸 **작업용** 사본. 정상 복구 지점(.env.last-good)과는 다르다.
# 이 파일은 "직전에 무엇이 돌고 있었나"이고, last-good은 "무엇이 검증됐나"다.
if [[ -f .env ]]; then
	cp .env .env.before-this-deploy
fi

# 데이터 관련 값은 deploy_data.sh가 쓴 것을 유지한다. 이미지와 커밋 줄만 교체한다.
touch .env
grep -v -e '^GEOLEOBOM_API_IMAGE=' -e '^GEOLEOBOM_DEPLOYED_SHA=' .env >.env.next || true
echo "GEOLEOBOM_API_IMAGE=$PINNED" >>.env.next
# 서버 설정(compose.yaml·Caddyfile)이 어느 커밋의 것인지 남긴다. 롤백이 이미지와
# 설정을 함께 되돌리는 근거다.
echo "GEOLEOBOM_DEPLOYED_SHA=$COMMIT_SHA" >>.env.next
mv .env.next .env
chmod 600 .env

# 위에서 digest로 이미 받았다. compose pull은 태그 기준이라 여기서 다시 부르지 않는다.
docker compose -f compose.yaml up -d

# **up -d 는 "만들었다"까지다.** 앱이 요청을 받는지는 따로 확인한다.
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
	# 컨테이너가 재시작을 반복하면 기다릴 이유가 없다.
	state="\$(docker inspect geoleobom-api --format '{{.State.Status}}' 2>/dev/null || echo missing)"
	if [[ "\$state" == "exited" || "\$state" == "dead" || "\$state" == "missing" ]]; then
		echo "   api 컨테이너 상태: \$state" >&2
		break
	fi
	sleep 2
done

if [[ \$ready -ne 1 ]]; then
	echo "API가 ${READY_TIMEOUT_S}s 안에 응답하지 않았다. 최근 로그:" >&2
	docker logs --tail 40 geoleobom-api 2>&1 >&2 || true
	exit 1
fi
echo "   API 응답 확인"

# 태그가 아니라 실제로 돌고 있는 이미지의 digest를 확인한다.
RUNNING="\$(docker inspect geoleobom-api --format '{{.Image}}')"
WANTED="\$(docker image inspect '$PINNED' --format '{{.Id}}')"
if [[ "\$RUNNING" != "\$WANTED" ]]; then
	echo "실행 중인 이미지가 배포하려던 것과 다르다: \$RUNNING != \$WANTED" >&2
	exit 1
fi
echo "실행 중 image id: \$RUNNING"

# Caddyfile은 바인드 마운트라 내용이 바뀌어도 compose가 컨테이너를 재생성하지
# 않는다. 복사만 하고 끝내면 **새 설정이 적용되지 않는다.** 실제로 겪었다 —
# 오류 로그 정제를 고쳐 올렸는데 옛 설정이 계속 돌았다.
#
# \`caddy reload\`는 먼저 설정을 검증하고 실패하면 돌던 설정을 그대로 둔다.
# 그래서 잘못된 Caddyfile을 올려도 서비스가 끊기지 않는다.
if docker exec geoleobom-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
	echo "Caddy 설정 재적용 완료"
else
	echo "Caddy 설정 재적용 실패 — 돌던 설정이 유지된다. Caddyfile을 확인해라" >&2
	exit 1
fi

docker compose -f compose.yaml ps
REMOTE

if [[ $SKIP_SMOKE -eq 1 ]]; then
	echo
	echo "기동과 응답까지 확인했다. **스모크를 건너뛰었으므로 정상 복구 지점은 갱신하지 않는다.**"
	echo "직접 돌려라: python deploy/smoke.py --base-url $BASE_URL"
	echo "배포된 이미지: $PINNED"
	exit 0
fi

echo
echo "== 6. 스모크 (픽스처 5좌표) — 통과해야 정상 복구 지점을 갱신한다"
# `|| true`가 필요하다. `.env`에 그 줄이 없으면 grep이 1을 반환하고, `set -e`와
# `pipefail` 때문에 **배포는 이미 반영된 뒤 스모크 전에** 스크립트가 죽는다.
# 기준값이 없으면 규약 불변식만 보면 되므로 여기서 멈출 이유가 없다.
DATA_VERSION="$(ssh "$HOST" "grep '^GEOLEOBOM_DATA_VERSION=' $REMOTE_DIR/.env | cut -d= -f2- || true" | tr -d '\r\n')"
BASELINE="$REPO_ROOT/deploy/smoke_baseline/$DATA_VERSION.json"
SMOKE_ARGS=(--base-url "$BASE_URL")
if [[ -n "$DATA_VERSION" && -f "$BASELINE" ]]; then
	SMOKE_ARGS+=(--baseline "$BASELINE")
	echo "   기준값: $BASELINE"
else
	echo "   기준값 없음($DATA_VERSION) — 규약 불변식만 확인한다"
fi

if ! python "$REPO_ROOT/deploy/smoke.py" "${SMOKE_ARGS[@]}"; then
	echo >&2
	echo "스모크 실패. **정상 복구 지점을 갱신하지 않는다.**" >&2
	echo "되돌리려면: bash deploy/rollback.sh code --host $HOST" >&2
	exit 1
fi

echo
echo "== 7. 정상 복구 지점 갱신"
ssh "$HOST" "cd '$REMOTE_DIR' && cp .env .env.last-good && chmod 600 .env.last-good"
echo "   .env.last-good = $COMMIT_SHA"
echo
echo "배포 완료. 이미지: $PINNED"
