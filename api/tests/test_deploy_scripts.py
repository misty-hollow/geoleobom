"""배포 스크립트가 지키기로 한 것 (v2.3 5절, AGENTS.md 5절).

스크립트는 서버 상태를 바꾸므로 CI에서 **실행해 볼 수 없다.** 여기서는 구조를 본다.
Caddy 로그 검사에서 겪었듯이, 구조 검사도 잘 쓰면 실제 결함을 잡는다.

Astra 감사가 짚은 네 가지를 고정한다. 넷 다 현재 main에서 코드로 확인했다.

1. `deploy_data.sh`가 기존 버전 디렉터리를 `mkdir -p` + `scp`로 **덮어썼다.**
2. `docker compose stop api osrm || true` — **정지 실패를 무시**하고 참조를 바꿨다.
3. `up -d` 직후 digest만 대조하고 "기동까지 확인했다"고 했다. **응답 대기가 없었다.**
4. 정상 복구 지점(`.env.previous`)을 **스모크 전에** 갱신했고, 롤백이 이미지만
   되돌려 **옛 이미지 + 새 compose/Caddyfile** 조합을 만들었다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
DEPLOY_API = DEPLOY / "deploy_api.sh"
DEPLOY_DATA = DEPLOY / "deploy_data.sh"
ROLLBACK = DEPLOY / "rollback.sh"


def _code(path: Path) -> str:
    """주석과 빈 줄을 뺀 본문. 주석에 적힌 문장이 검사를 통과시키지 않게 한다."""
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(raw)
    return "\n".join(lines)


@pytest.fixture(scope="module")
def deploy_api() -> str:
    return _code(DEPLOY_API)


@pytest.fixture(scope="module")
def deploy_data() -> str:
    return _code(DEPLOY_DATA)


@pytest.fixture(scope="module")
def rollback() -> str:
    return _code(ROLLBACK)


# --- 1. data_version 불변성 ---------------------------------------------------


def test_data_deploy_refuses_to_write_into_an_existing_version(deploy_data: str):
    """이미 있는 버전 디렉터리에 업로드하면 멈춘다.

    `data_version`은 캐시 키(v2.3 4-3)와 응답 `versions`에 들어간다. 같은 이름으로
    내용을 바꾸면 옛 캐시 결과가 새 데이터인 척 남는다.
    """
    assert "test -e '$DATA_ROOT/$VERSION'" in deploy_data, "기존 버전 존재 검사가 없다"
    assert "기존 버전에 덮어쓰지 않는다" in deploy_data


def test_data_deploy_uploads_through_staging_then_moves(deploy_data: str):
    """반쯤 올라간 디렉터리가 `current`가 되지 않게 staging을 거쳐 옮긴다."""
    assert "DATA_ROOT/.staging" in deploy_data, "staging 경로를 쓰지 않는다"
    assert 'mv "\\$STAGING" "\\$DATA_ROOT/\\$VERSION"' in deploy_data, "원자적 이동이 없다"
    # 제자리에 바로 만들던 옛 형태가 남아 있으면 안 된다.
    assert "mkdir -p '$DATA_ROOT/$VERSION" not in deploy_data


def test_data_deploy_rejects_path_like_version_names(deploy_data: str):
    """버전 이름이 경로가 되므로 `..`이나 `/`가 들어오면 엉뚱한 곳을 건드린다."""
    assert '"$VERSION" =~ ^[A-Za-z0-9._-]+$' in deploy_data
    for reserved in ("current", "previous", ".staging"):
        assert reserved in deploy_data


def test_data_deploy_verifies_the_version_bundle(deploy_data: str):
    """poi.gpkg · OSRM 파일 세트 · poi_date가 **같은 묶음**인지 확인한다."""
    assert "MANIFEST" in deploy_data, "묶음 명세를 남기지 않는다"
    assert "poi_gpkg_sha256" in deploy_data
    assert "chungcheong.osrm.fileIndex" in deploy_data
    assert "poi_date.txt" in deploy_data
    # 지정한 poi_date가 그 버전의 것과 다르면 멈춘다.
    assert "기준일을 바꾸려면 새 data_version을 만든다" in deploy_data


# --- 2. 정지 실패를 무시하지 않는다 -------------------------------------------


@pytest.mark.parametrize("script", ["deploy_data", "rollback"])
def test_stopping_containers_is_not_ignored(script: str, request: pytest.FixtureRequest):
    """`docker compose stop ... || true`는 정지 실패를 삼킨다.

    정지가 실패하면 옛 데이터를 연 프로세스가 남고, 그 상태로 참조를 바꾸면
    무엇을 읽고 있는지 알 수 없다(v2.3 5절: 실행 중 파일 덮어쓰기 금지).
    """
    text: str = request.getfixturevalue(script)
    assert "stop api osrm || true" not in text, "정지 실패를 무시한다"
    assert "if ! docker compose -f compose.yaml stop api osrm; then" in text


def test_data_deploy_confirms_containers_actually_stopped(deploy_data: str):
    """명령이 0을 반환한 것과 실제로 멈춘 것을 구분한다."""
    assert "docker inspect" in deploy_data
    assert "exited | created | missing" in deploy_data


# --- 3. up -d 와 실제 기동을 구분한다 -----------------------------------------


@pytest.mark.parametrize("script", ["deploy_api", "deploy_data", "rollback"])
def test_readiness_is_checked_with_a_timeout(script: str, request: pytest.FixtureRequest):
    """`up -d` 성공은 "컨테이너를 만들었다"이지 "앱이 응답한다"가 아니다.

    실제로 겪었다 — httpx가 dev 의존성이라 이미지는 멀쩡히 만들어졌는데 컨테이너가
    ModuleNotFoundError로 죽었다. 제한시간을 두고 `/api/health`를 확인한다.
    """
    text: str = request.getfixturevalue(script)
    assert "READY_TIMEOUT_S" in text, "응답 대기 제한시간이 없다"
    assert "/api/health" in text, "readiness 확인이 없다"
    assert "deadline=" in text and "date +%s" in text, "제한시간 루프가 없다"
    # 죽은 컨테이너를 제한시간 끝까지 기다리지 않는다.
    assert "exited" in text and "dead" in text


def test_data_deploy_waits_for_the_new_data_version_specifically(deploy_data: str):
    """응답만 오는 것으로는 부족하다. **바뀐 버전으로** 답해야 반영된 것이다."""
    assert "data_version" in deploy_data
    assert 'if [[ "\\$got" == "\\$VERSION" ]]' in deploy_data


# --- 4. 정상 복구 지점과 설정·이미지의 짝 -------------------------------------


def test_the_recovery_point_advances_only_after_smoke(deploy_api: str):
    """스모크 통과 뒤에만 `.env.last-good`을 갱신한다.

    예전에는 배포를 시작하면서 직전 `.env`를 `.env.previous`로 복사했다. 깨진 배포를
    두 번 연속 하면 복구 지점이 깨진 쪽을 가리킨다.
    """
    assert ".env.last-good" in deploy_api
    smoke_index = deploy_api.index("smoke.py")
    last_good_index = deploy_api.index("cp .env .env.last-good")
    assert smoke_index < last_good_index, "스모크보다 먼저 복구 지점을 갱신한다"
    assert "정상 복구 지점을 갱신하지 않는다" in deploy_api


def test_skipping_smoke_does_not_advance_the_recovery_point(deploy_api: str):
    assert "--skip-smoke" in deploy_api
    assert "스모크를 건너뛰었으므로 정상 복구 지점은 갱신하지 않는다" in deploy_api


def test_deploy_records_the_commit_whose_config_was_applied(deploy_api: str):
    """설정(compose.yaml·Caddyfile)이 어느 커밋의 것인지 남긴다."""
    assert "GEOLEOBOM_DEPLOYED_SHA" in deploy_api


def test_deploy_uploads_the_config_from_that_commit_not_the_worktree(deploy_api: str):
    """작업 트리의 수정본을 올리면 서버 설정이 어느 커밋의 것인지 알 수 없다."""
    assert 'git -C "$REPO_ROOT" archive "$COMMIT_SHA" deploy' in deploy_api
    # 작업 트리에서 바로 올리던 옛 형태.
    assert '"$REPO_ROOT/deploy/compose.yaml"' not in deploy_api


def test_code_rollback_restores_config_and_image_together(rollback: str):
    """옛 이미지에 새 compose/Caddyfile을 섞지 않는다.

    그 조합은 어디서도 검사된 적이 없다.
    """
    assert "GEOLEOBOM_DEPLOYED_SHA" in rollback
    assert 'git -C "$REPO_ROOT" archive "$PREV_SHA" deploy' in rollback
    assert "caddy reload" in rollback, "설정을 되돌리고 Caddy를 다시 읽히지 않는다"


def test_code_rollback_reads_the_smoke_verified_recovery_point(rollback: str):
    assert ".env.last-good" in rollback
    # 이전 방식 파일로 되돌아가는 경로가 있다면 그것이 검증 기록이 아님을 말해야 한다.
    assert "스모크 통과 기록이 아니다" in rollback


def test_data_rollback_checks_the_previous_bundle_before_touching_anything(rollback: str):
    """정지·링크 교체 **전에** 사전조건을 전부 본다."""
    body = rollback[rollback.index("data)") :]
    stop_index = body.index("docker compose -f compose.yaml stop api osrm")
    for precondition in (
        "poi.gpkg",
        "chungcheong.osrm.fileIndex",
        "poi_date.txt",
        "MANIFEST",
    ):
        assert body.index(precondition) < stop_index, f"{precondition} 검사가 정지 뒤에 있다"


def test_data_rollback_never_deletes(rollback: str):
    """되돌리기가 데이터를 지우면 다시 앞으로 갈 수 없다(AGENTS.md 5절)."""
    body = rollback[rollback.index("data)") :]
    for destructive in ("rm -rf", "rm -f "):
        assert destructive not in body, f"데이터 롤백이 {destructive} 를 쓴다"


# --- 문서와 예시 --------------------------------------------------------------


def test_usage_examples_do_not_upload_into_an_existing_version(deploy_data: str):
    """예시가 기존 버전 경로를 재사용하면 사람이 그대로 따라 하다 막힌다.

    주석까지 포함해 본다 — 사람이 읽는 것은 주석이다.
    """
    text = DEPLOY_DATA.read_text(encoding="utf-8")
    examples = [
        line for line in text.splitlines() if "--upload" in line and line.strip().startswith("#")
    ]
    assert examples, "업로드 예시가 없다"
    for line in examples:
        assert "--version 2026Q3-cc-01" not in line, f"이미 배포된 버전을 예시로 쓴다: {line}"
        assert "--version synthetic-cc-01" not in line, f"이미 배포된 버전을 예시로 쓴다: {line}"
    assert "버전 이름을 그대로 재사용하지 마라" in text
