#!/usr/bin/env bash
# 데이터 배포본 교체 (v2.3 5절 "데이터 교체 절차(확정)").
#
# 절차 그대로다:
#   새 버전 디렉터리 업로드 → api·osrm 정지 → 참조 변경 → 재기동(마운트 설정이
#   바뀌면 컨테이너 재생성) → 픽스처 5좌표 스모크 테스트 → 직전 버전 1개 보존
#
# **실행 중 파일 덮어쓰기와 단순 restart만으로 갱신을 끝내지 않는다.**
# 코드 배포(deploy_api.sh)와 분리한다. AGENTS.md 5절.
#
# 사용법 (개발 PC에서):
#   bash deploy/deploy_data.sh --version synthetic-cc-01 --poi-date synthetic
#   bash deploy/deploy_data.sh --version 2026Q3-cc-01 --poi-date 2026-07-01 --upload data/build/2026Q3-cc-01
#
# --upload를 주면 그 로컬 디렉터리를 서버의 버전 디렉터리로 올린다. 생략하면
# 이미 올라가 있는 버전으로 참조만 바꾼다(롤백·재지정).
#
# 스모크는 이 스크립트가 돌리지 않는다. 끝난 뒤 deploy/smoke.py를 돌린다.

set -euo pipefail

HOST="geoleobom"
DATA_ROOT="/srv/geoleobom/data"
REMOTE_DIR="/opt/geoleobom"
VERSION=""
POI_DATE=""
UPLOAD_DIR=""

usage() {
	echo "usage: $0 --version <data_version> --poi-date <date> [--upload <local-dir>] [--host <ssh-host>]" >&2
	exit 2
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--version)
		VERSION="${2:?}"
		shift 2
		;;
	--poi-date)
		POI_DATE="${2:?}"
		shift 2
		;;
	--upload)
		UPLOAD_DIR="${2:?}"
		shift 2
		;;
	--host)
		HOST="${2:?}"
		shift 2
		;;
	*) usage ;;
	esac
done

[[ -n "$VERSION" && -n "$POI_DATE" ]] || usage

if [[ -n "$UPLOAD_DIR" ]]; then
	echo "== 0. 새 버전 디렉터리 업로드: $UPLOAD_DIR -> $DATA_ROOT/$VERSION"
	[[ -f "$UPLOAD_DIR/poi.gpkg" ]] || {
		echo "$UPLOAD_DIR/poi.gpkg 가 없다" >&2
		exit 1
	}
	[[ -d "$UPLOAD_DIR/osrm" ]] || {
		echo "$UPLOAD_DIR/osrm 디렉터리가 없다" >&2
		exit 1
	}
	ssh "$HOST" "mkdir -p '$DATA_ROOT/$VERSION/osrm'"
	scp -q "$UPLOAD_DIR/poi.gpkg" "$HOST:$DATA_ROOT/$VERSION/poi.gpkg"
	# 큰 파일이라 tar 스트림으로 한 번에 보낸다.
	tar -czf - -C "$UPLOAD_DIR/osrm" . | ssh "$HOST" "tar -xzf - -C '$DATA_ROOT/$VERSION/osrm'"
fi

ssh "$HOST" "bash -s" <<REMOTE
set -euo pipefail
DATA_ROOT="$DATA_ROOT"
VERSION="$VERSION"
POI_DATE="$POI_DATE"
cd "$REMOTE_DIR"

echo "== 1. 새 버전 디렉터리 확인"
test -f "\$DATA_ROOT/\$VERSION/poi.gpkg" || { echo "poi.gpkg 없음"; exit 1; }
# compose의 osrm command가 이 이름을 고정한다. 다른 이름이면 검사만 통과하고
# osrm이 기동에 실패해 재시작을 반복한다.
test -f "\$DATA_ROOT/\$VERSION/osrm/chungcheong.osrm.fileIndex" || {
	echo "osrm 파일 세트가 없거나 이름이 chungcheong.osrm.*가 아니다 (compose osrm command와 맞춰야 한다)"
	ls "\$DATA_ROOT/\$VERSION/osrm" 2>/dev/null | head
	exit 1
}
du -sh "\$DATA_ROOT/\$VERSION"

echo "== 2. api·osrm 정지 (실행 중 덮어쓰기를 하지 않는다)"
docker compose -f compose.yaml stop api osrm || true

echo "== 3. 기준일을 버전 디렉터리에 함께 기록"
# poi_date는 그 데이터의 성질이지 서버 설정이 아니다. 버전 디렉터리에 같이 두면
# 롤백이 데이터와 기준일을 항상 짝지어 되돌릴 수 있다. .env만 보고 되돌리면
# 데이터는 옛 버전인데 기준일은 새 버전 값이 남는 사고가 난다.
echo "\$POI_DATE" > "\$DATA_ROOT/\$VERSION/poi_date.txt"

echo "== 4. 참조 변경 (직전 버전을 previous로 보존)"
if [[ -L "\$DATA_ROOT/current" ]]; then
	PREVIOUS="\$(readlink "\$DATA_ROOT/current")"
	# 같은 버전을 다시 지정하는 경우(재기동·재지정) previous를 덮어쓰지 않는다.
	# 덮어쓰면 previous == current가 되어 롤백이 제자리걸음을 하며 "되돌렸다"고
	# 보고한다. v2.3 5절의 "직전 버전 1개 보존(롤백용)"이 깨진다.
	if [[ -n "\$PREVIOUS" && "\$PREVIOUS" != "\$VERSION" ]]; then
		echo "   직전 버전: \$PREVIOUS"
		ln -sfn "\$PREVIOUS" "\$DATA_ROOT/previous"
	else
		echo "   같은 버전 재지정 — previous를 그대로 둔다"
	fi
fi
ln -sfn "\$VERSION" "\$DATA_ROOT/current"
ls -l "\$DATA_ROOT/current" "\$DATA_ROOT/previous" 2>/dev/null || true

# 컨테이너가 읽는 값. deploy_api.sh가 쓴 이미지 줄은 건드리지 않는다.
touch .env
grep -v -e '^GEOLEOBOM_DATA_VERSION=' -e '^GEOLEOBOM_POI_DATE=' .env > .env.next || true
echo "GEOLEOBOM_DATA_VERSION=\$VERSION" >> .env.next
echo "GEOLEOBOM_POI_DATE=\$POI_DATE" >> .env.next
mv .env.next .env
chmod 600 .env

echo "== 5. 재기동 (마운트·환경이 바뀌었으므로 컨테이너를 재생성한다)"
# 아직 이미지를 배포하지 않았으면 api를 올리지 않는다. compose 기본값은 레지스트리에
# 없는 태그라 pull이 실패하고, 그러면 데이터 반영까지 같이 실패한 것처럼 보인다.
# 첫 배포에서는 데이터를 먼저 올리고 deploy_api.sh가 api를 붙이는 순서가 된다.
if grep -q '^GEOLEOBOM_API_IMAGE=' .env; then
	docker compose -f compose.yaml up -d --force-recreate api osrm
else
	echo "   GEOLEOBOM_API_IMAGE가 아직 없다 — osrm만 올린다. 다음에 deploy_api.sh를 돌린다."
	docker compose -f compose.yaml up -d --force-recreate osrm
fi
docker compose -f compose.yaml ps

echo "== 6. 직전 버전 1개만 남기고 정리 대상 확인 (삭제는 하지 않는다)"
ls -1 "\$DATA_ROOT" | grep -v -e '^current\$' -e '^previous\$' || true
REMOTE

echo
echo "데이터 참조를 $VERSION 으로 바꿨다. 다음: python deploy/smoke.py --base-url https://geoleobom.kr"
echo "직전 버전은 $DATA_ROOT/previous 에 남아 있다. 롤백은 deploy/rollback.sh."
