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
# ## data_version은 불변이다
#
# 이미 있는 버전 디렉터리에는 **쓰지 않는다.** 예전에는 `mkdir -p` + `scp`라서
# 같은 `--version`으로 다시 돌리면 돌고 있는 배포본 위에 덮어썼다. 그러면
#   - `data_version`이 같은데 내용이 다른 파일이 생기고,
#   - 캐시 키가 `data_version`을 쓰므로(v2.3 4-3) **옛 결과가 새 데이터인 척** 남고,
#   - `previous`로 되돌아가도 그 버전이 무엇이었는지 아무도 모른다.
# 데이터를 고쳤으면 새 `data_version`을 만든다. 이 스크립트가 그것을 강제한다.
#
# 업로드는 `.staging/<버전>`에 받아 검증한 뒤 **원자적으로 옮긴다.** 중간에 끊겨도
# 반쯤 찬 버전 디렉터리가 `current`가 될 일이 없다.
#
# ## 사용법 (개발 PC에서)
#
#   # 새 배포본 올리기 — OSRM 그래프까지 함께 올린다
#   bash deploy/deploy_data.sh --version 2026Q3-cc-04 --poi-date 2026-06-30 \
#       --upload data/build/2026Q3-cc-04
#
#   # POI만 바뀌고 보행망은 그대로일 때 — 그래프를 서버에서 복사한다(재업로드 없음)
#   bash deploy/deploy_data.sh --version 2026Q3-cc-04 --poi-date 2026-06-30 \
#       --upload data/build/2026Q3-cc-04 --osrm-from 2026Q3-cc-03
#
#   # 이미 올라간 버전으로 참조만 바꾸기 (롤백·재지정). 업로드하지 않는다.
#   bash deploy/deploy_data.sh --version 2026Q3-cc-03 --poi-date 2026-06-30
#
# **위 예시의 버전 이름을 그대로 재사용하지 마라.** 이미 서버에 있는 버전에
# `--upload`를 걸면 스크립트가 거부한다. 그게 의도다.
#
# 스모크는 이 스크립트가 돌리지 않는다. 끝난 뒤 deploy/smoke.py를 돌린다.

set -euo pipefail

HOST="geoleobom"
DATA_ROOT="/srv/geoleobom/data"
REMOTE_DIR="/opt/geoleobom"
VERSION=""
POI_DATE=""
UPLOAD_DIR=""
OSRM_FROM=""
READY_TIMEOUT_S=120

usage() {
	cat >&2 <<'USAGE'
usage: deploy_data.sh --version <data_version> --poi-date <date>
                      [--upload <local-dir>] [--osrm-from <existing-version>]
                      [--host <ssh-host>]

  --upload      새 버전 디렉터리를 올린다. 이미 있는 버전이면 거부한다.
  --osrm-from   OSRM 그래프를 그 버전에서 서버 안에서 복사한다(재업로드 없음).
                보행망이 바뀌지 않고 POI만 바뀐 배포본에 쓴다.
USAGE
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
	--osrm-from)
		OSRM_FROM="${2:?}"
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

# 버전 이름이 경로가 되므로 모양을 고정한다. `..`이나 `/`가 들어오면 staging·current
# 조작이 엉뚱한 곳을 가리킨다.
#
# **첫 글자를 영숫자로 강제한다.** `[A-Za-z0-9._-]+` 만으로는 `.`·`..`·`-x`가 통과한다.
# 뒤쪽 검사(`test -e`, `test -s .../poi.gpkg`)가 결국 막기는 하지만, 이름 검사가
# 막는다고 적어 놓고 실제로는 안 막는 상태를 두지 않는다.
if [[ ! "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
	echo "data_version은 영숫자로 시작하고 영숫자와 . _ - 만 쓴다: $VERSION" >&2
	exit 2
fi
for reserved in current previous .staging; do
	if [[ "$VERSION" == "$reserved" ]]; then
		echo "예약된 이름은 data_version으로 쓸 수 없다: $VERSION" >&2
		exit 2
	fi
done
if [[ -n "$OSRM_FROM" && -z "$UPLOAD_DIR" ]]; then
	echo "--osrm-from은 --upload와 함께 쓴다" >&2
	exit 2
fi

if [[ -n "$UPLOAD_DIR" ]]; then
	echo "== 0. 새 버전 업로드 준비: $UPLOAD_DIR -> $DATA_ROOT/$VERSION"
	[[ -f "$UPLOAD_DIR/poi.gpkg" ]] || {
		echo "$UPLOAD_DIR/poi.gpkg 가 없다" >&2
		exit 1
	}
	if [[ -z "$OSRM_FROM" ]]; then
		[[ -d "$UPLOAD_DIR/osrm" ]] || {
			echo "$UPLOAD_DIR/osrm 디렉터리가 없다 (--osrm-from으로 기존 그래프를 쓸 수도 있다)" >&2
			exit 1
		}
	fi

	# **불변성 가드.** 이미 있는 버전에는 쓰지 않는다.
	if ssh "$HOST" "test -e '$DATA_ROOT/$VERSION'"; then
		cat >&2 <<GUARD
$DATA_ROOT/$VERSION 이 이미 있다. **기존 버전에 덮어쓰지 않는다.**

data_version은 캐시 키(v2.3 4-3)와 응답의 versions에 들어간다. 같은 이름으로
내용을 바꾸면 옛 캐시 결과가 새 데이터인 척 남고, 롤백해도 그 버전이 무엇이었는지
알 수 없다. 데이터를 고쳤으면 새 data_version을 만들어라.

참조만 바꾸려면 --upload 없이 실행한다:
  bash deploy/deploy_data.sh --version $VERSION --poi-date $POI_DATE
GUARD
		exit 1
	fi

	STAGING="$DATA_ROOT/.staging/$VERSION"
	# 끊긴 앞선 시도가 남아 있을 수 있다. staging은 아직 아무도 안 보는 곳이라 지워도 된다.
	ssh "$HOST" "rm -rf '$STAGING' && mkdir -p '$STAGING/osrm'"
	scp -q "$UPLOAD_DIR/poi.gpkg" "$HOST:$STAGING/poi.gpkg"
	if [[ -n "$OSRM_FROM" ]]; then
		echo "   OSRM 그래프를 서버 안에서 복사: $OSRM_FROM -> $VERSION"
		ssh "$HOST" "bash -s" <<COPY
set -euo pipefail
test -f '$DATA_ROOT/$OSRM_FROM/osrm/chungcheong.osrm.fileIndex' || {
	echo '--osrm-from 버전에 OSRM 파일 세트가 없다: $OSRM_FROM' >&2
	exit 1
}
cp -a '$DATA_ROOT/$OSRM_FROM/osrm/.' '$STAGING/osrm/'
COPY
	else
		# 큰 파일이라 tar 스트림으로 한 번에 보낸다.
		tar -czf - -C "$UPLOAD_DIR/osrm" . | ssh "$HOST" "tar -xzf - -C '$STAGING/osrm'"
	fi

	echo "== 0b. staging 검증 후 원자적으로 옮긴다"
	ssh "$HOST" "bash -s" <<STAGE
set -euo pipefail
STAGING="$STAGING"
VERSION="$VERSION"
POI_DATE="$POI_DATE"
DATA_ROOT="$DATA_ROOT"

# **한 버전 묶음이 온전한지** 여기서 본다. current로 만든 뒤에 확인하면 이미 늦다.
test -s "\$STAGING/poi.gpkg" || { echo 'poi.gpkg가 비었다'; exit 1; }
# compose의 osrm command가 이 이름을 고정한다. 다른 이름이면 검사만 통과하고
# osrm이 기동에 실패해 재시작을 반복한다.
for required in fileIndex mldgr ebg nbg_nodes; do
	test -s "\$STAGING/osrm/chungcheong.osrm.\$required" || {
		echo "osrm 파일 세트가 온전하지 않다: chungcheong.osrm.\$required 없음"
		ls "\$STAGING/osrm" 2>/dev/null | head
		exit 1
	}
done

# poi_date는 그 데이터의 성질이지 서버 설정이 아니다. 버전 디렉터리에 같이 두면
# 롤백이 데이터와 기준일을 항상 짝지어 되돌릴 수 있다. .env만 보고 되돌리면
# 데이터는 옛 버전인데 기준일은 새 버전 값이 남는 사고가 난다.
echo "\$POI_DATE" > "\$STAGING/poi_date.txt"

# 묶음 명세. **세 가지가 같은 버전의 것임을 나중에도 확인할 수 있게** 남긴다.
{
	echo "data_version=\$VERSION"
	echo "poi_date=\$POI_DATE"
	echo "poi_gpkg_sha256=\$(sha256sum "\$STAGING/poi.gpkg" | cut -d' ' -f1)"
	echo "poi_gpkg_bytes=\$(stat -c %s "\$STAGING/poi.gpkg")"
	echo "osrm_files=\$(find "\$STAGING/osrm" -type f | wc -l)"
	echo "osrm_bytes=\$(du -sb "\$STAGING/osrm" | cut -f1)"
	echo "osrm_fileindex_sha256=\$(sha256sum "\$STAGING/osrm/chungcheong.osrm.fileIndex" | cut -d' ' -f1)"
	echo "uploaded_at=\$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "\$STAGING/MANIFEST"

# 여기까지 왔으면 온전하다. **원자적으로** 제자리에 놓는다.
test ! -e "\$DATA_ROOT/\$VERSION" || { echo '경쟁: 버전 디렉터리가 그 사이에 생겼다'; exit 1; }
mv "\$STAGING" "\$DATA_ROOT/\$VERSION"
rmdir "\$DATA_ROOT/.staging" 2>/dev/null || true
cat "\$DATA_ROOT/\$VERSION/MANIFEST"
STAGE
fi

ssh "$HOST" "bash -s" <<REMOTE
set -euo pipefail
DATA_ROOT="$DATA_ROOT"
VERSION="$VERSION"
POI_DATE="$POI_DATE"
cd "$REMOTE_DIR"

echo "== 1. 버전 묶음 확인 (poi.gpkg · OSRM · poi_date가 같은 묶음인가)"
test -d "\$DATA_ROOT/\$VERSION" || { echo "버전 디렉터리가 없다: \$VERSION"; exit 1; }
test -s "\$DATA_ROOT/\$VERSION/poi.gpkg" || { echo "poi.gpkg 없음"; exit 1; }
test -s "\$DATA_ROOT/\$VERSION/osrm/chungcheong.osrm.fileIndex" || {
	echo "osrm 파일 세트가 없거나 이름이 chungcheong.osrm.*가 아니다 (compose osrm command와 맞춰야 한다)"
	ls "\$DATA_ROOT/\$VERSION/osrm" 2>/dev/null | head
	exit 1
}

# MANIFEST가 있으면 **올릴 때 기록한 내용과 지금이 같은지** 본다.
#
# 없으면 **대조를 건너뛴다. 지금 만들지 않는다.** MANIFEST를 쓰기 전에 올라간 버전이
# 서버에 남아 있는데, 지금 만들면 "올릴 때의 상태"가 아니라 "지금 상태"를 기록하게 된다.
# 이미 손댄 파일이라도 그 상태가 정답으로 굳어져 **없는 보장을 있는 것처럼 만든다.**
# 옛 버전에 명세가 필요하면 사람이 근거를 확인하고 따로 만든다.
if [[ -f "\$DATA_ROOT/\$VERSION/MANIFEST" ]]; then
	want_sha="\$(grep '^poi_gpkg_sha256=' "\$DATA_ROOT/\$VERSION/MANIFEST" | cut -d= -f2-)"
	have_sha="\$(sha256sum "\$DATA_ROOT/\$VERSION/poi.gpkg" | cut -d' ' -f1)"
	if [[ "\$want_sha" != "\$have_sha" ]]; then
		echo "poi.gpkg가 MANIFEST와 다르다. 이 버전 디렉터리가 손댄 흔적이 있다." >&2
		echo "  기록 \$want_sha" >&2
		echo "  현재 \$have_sha" >&2
		exit 1
	fi
	want_date="\$(grep '^poi_date=' "\$DATA_ROOT/\$VERSION/MANIFEST" | cut -d= -f2-)"
	if [[ "\$want_date" != "\$POI_DATE" ]]; then
		echo "poi_date가 이 버전의 것과 다르다: 기록 '\$want_date' != 지정 '\$POI_DATE'" >&2
		echo "poi_date는 데이터의 성질이다. 버전마다 하나뿐이다." >&2
		exit 1
	fi
	echo "   MANIFEST 대조 통과"
else
	echo "   ** MANIFEST 없음 — 묶음 대조를 건너뛴다 (MANIFEST 이전에 올라간 버전) **"
fi

# 버전 디렉터리의 poi_date와 지정한 값이 어긋나면 멈춘다. 둘이 갈리면 화면에
# 보여줄 기준일과 실제 데이터가 달라진다(v2.3 4-5).
if [[ -f "\$DATA_ROOT/\$VERSION/poi_date.txt" ]]; then
	existing="\$(cat "\$DATA_ROOT/\$VERSION/poi_date.txt")"
	if [[ "\$existing" != "\$POI_DATE" ]]; then
		echo "이 버전의 poi_date는 '\$existing'인데 '\$POI_DATE'를 지정했다." >&2
		echo "기준일을 바꾸려면 새 data_version을 만든다." >&2
		exit 1
	fi
else
	echo "\$POI_DATE" > "\$DATA_ROOT/\$VERSION/poi_date.txt"
fi
du -sh "\$DATA_ROOT/\$VERSION"

echo "== 2. api·osrm 정지 (실행 중 덮어쓰기를 하지 않는다)"
# **정지 실패를 무시하지 않는다.** 예전에는 \`|| true\`였다. 정지가 실패하면 옛
# 데이터를 연 채로 돌고 있는 프로세스가 남고, 그 상태에서 참조를 바꾸면 무엇을
# 읽고 있는지 알 수 없다.
if ! docker compose -f compose.yaml stop api osrm; then
	echo "api·osrm 정지에 실패했다. 참조를 바꾸지 않고 멈춘다." >&2
	docker compose -f compose.yaml ps >&2 || true
	exit 1
fi
for name in geoleobom-api geoleobom-osrm; do
	state="\$(docker inspect "\$name" --format '{{.State.Status}}' 2>/dev/null || echo missing)"
	case "\$state" in
	exited | created | missing) ;;
	*)
		echo "\$name 이 아직 \$state 다. 멈춘다." >&2
		exit 1
		;;
	esac
done
echo "   정지 확인"

echo "== 3. 참조 변경 (직전 버전을 previous로 보존)"
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

echo "== 4. 재기동 (마운트·환경이 바뀌었으므로 컨테이너를 재생성한다)"
# 아직 이미지를 배포하지 않았으면 api를 올리지 않는다. compose 기본값은 레지스트리에
# 없는 태그라 pull이 실패하고, 그러면 데이터 반영까지 같이 실패한 것처럼 보인다.
# 첫 배포에서는 데이터를 먼저 올리고 deploy_api.sh가 api를 붙이는 순서가 된다.
if grep -q '^GEOLEOBOM_API_IMAGE=' .env; then
	docker compose -f compose.yaml up -d --force-recreate api osrm

	echo "== 5. API 응답 대기 (최대 ${READY_TIMEOUT_S}s) — up -d 성공은 기동 성공이 아니다"
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
		if [[ "\$got" == "\$VERSION" ]]; then
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
		echo "API가 \$VERSION 으로 응답하지 않는다. 최근 로그:" >&2
		docker logs --tail 40 geoleobom-api 2>&1 >&2 || true
		docker logs --tail 20 geoleobom-osrm 2>&1 >&2 || true
		exit 1
	fi
	echo "   /api/health data_version = \$VERSION"
else
	echo "   GEOLEOBOM_API_IMAGE가 아직 없다 — osrm만 올린다. 다음에 deploy_api.sh를 돌린다."
	docker compose -f compose.yaml up -d --force-recreate osrm
fi
docker compose -f compose.yaml ps

echo "== 6. 보관 중인 버전 (삭제는 하지 않는다)"
ls -1 "\$DATA_ROOT" | grep -v -e '^current\$' -e '^previous\$' -e '^\.staging\$' || true
REMOTE

echo
echo "데이터 참조를 $VERSION 으로 바꿨다."
echo "**아직 검증 전이다.** 다음: python deploy/smoke.py --base-url https://geoleobom.kr"
echo "직전 버전은 $DATA_ROOT/previous 에 남아 있다. 롤백은 deploy/rollback.sh data."
