#!/usr/bin/env bash
# 코드 배포: GHCR 이미지를 커밋 SHA 태그 + digest로 고정해 서버에 반영한다.
#
# 기준: v2.3 4-1(서버에서 빌드하지 않는다), 5절(서버 구성), AGENTS.md 5절.
# **데이터 교체와 분리한다.** 데이터는 deploy/deploy_data.sh가 담당한다.
#
# 사용법 (개발 PC에서):
#   bash deploy/deploy_api.sh <커밋 SHA>
#   bash deploy/deploy_api.sh <커밋 SHA> --host geoleobom
#
# 하는 일:
#   1. 레지스트리에서 그 태그의 digest를 조회한다(태그만 믿지 않는다).
#   2. deploy/ 설정을 서버 /opt/geoleobom에 복사한다.
#   3. 직전 .env를 .env.previous로 보존한다(롤백용).
#   4. 태그 + digest를 .env에 적고 pull → up -d 한다.
#   5. 실제로 그 digest가 돌고 있는지 컨테이너에서 확인한다.
#
# 배포가 끝났다고 보고하기 전에 deploy/smoke.py를 돌린다. 이 스크립트는 기동까지만 한다.

set -euo pipefail

HOST="geoleobom"
REMOTE_DIR="/opt/geoleobom"
IMAGE_REPO="ghcr.io/misty-hollow/geoleobom-api"

usage() {
	echo "usage: $0 <commit-sha> [--host <ssh-host>]" >&2
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
	*) usage ;;
	esac
done

if [[ ! "$COMMIT_SHA" =~ ^[0-9a-f]{40}$ ]]; then
	echo "커밋 SHA 40자를 그대로 넣는다(브랜치 이름·latest 금지): $COMMIT_SHA" >&2
	exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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

echo "== 2. 배포 설정 복사"
scp -q "$REPO_ROOT/deploy/compose.yaml" "$REPO_ROOT/deploy/Caddyfile" "$HOST:$REMOTE_DIR/"
scp -q -r "$REPO_ROOT/deploy/site" "$HOST:$REMOTE_DIR/"

echo "== 3~5. .env 갱신 → pull → up -d → 실행 중인 digest 확인"
ssh "$HOST" "bash -s" <<REMOTE
set -euo pipefail
cd "$REMOTE_DIR"

# 직전 설정을 남긴다. 롤백은 이 파일을 되돌린다.
if [[ -f .env ]]; then
	cp .env .env.previous
fi

# 데이터 관련 값은 deploy_data.sh가 쓴 것을 유지한다. 이미지 줄만 교체한다.
touch .env
grep -v '^GEOLEOBOM_API_IMAGE=' .env >.env.next || true
echo "GEOLEOBOM_API_IMAGE=$PINNED" >>.env.next
mv .env.next .env
chmod 600 .env

# 위에서 digest로 이미 받았다. compose pull은 태그 기준이라 여기서 다시 부르지 않는다.
docker compose -f compose.yaml up -d

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
# `caddy reload`는 먼저 설정을 검증하고 실패하면 돌던 설정을 그대로 둔다.
# 그래서 잘못된 Caddyfile을 올려도 서비스가 끊기지 않는다.
if docker exec geoleobom-caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
	echo "Caddy 설정 재적용 완료"
else
	echo "Caddy 설정 재적용 실패 — 돌던 설정이 유지된다. Caddyfile을 확인해라" >&2
	exit 1
fi

docker compose -f compose.yaml ps
REMOTE

echo
echo "기동까지 확인했다. 다음: python deploy/smoke.py --base-url https://geoleobom.kr"
echo "배포된 이미지: $PINNED"
