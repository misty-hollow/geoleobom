"""롤백 스모크는 **되돌린 산출물의 계약**으로 돈다 (Astra delta D3).

## 무엇이 문제였나

`deploy/smoke.py`는 이 PR에서 의미 불변식을 얻었다 — `/route`의 출발지가 분석의
`snapped`와 같은 지점이어야 한다(v2.4 4-3 10단계). 좋은 검사지만, **되돌리는 산출물이
그 계약보다 이전이면 성립할 수 없다.**

    base 9212bcf의 API      : `/api/route` -> 501 (그때는 범위 밖이었다)
    base 9212bcf의 스모크    : `/api/route`를 부르지 않는다
    지금 스모크             : `/route` 200과 출발지 일치를 요구한다

그런데 `rollback.sh`는 그 커밋의 설정·이미지를 되돌린 뒤 **작업 트리의** 스모크를
돌리라고 안내했다. 정상 롤백인데 스모크가 실패한다. Astra가 직접 대조한 값:

    옛 스모크 + /route 501 -> exit 0
    현재 스모크 + /route 501 -> exit 1
    현재 스모크 + 정상 route -> exit 0

## 무엇으로 고쳤나

검사 논리가 아니라 **어느 검사를 쓰는가**를 고쳤다. `"501이면 건너뛴다"`는 금지다 —
현재 배포본에서 /route가 501이면 그것은 진짜 결함인데 통과해 버린다.

    현재 배포 -> 작업 트리의 deploy/smoke.py    (deploy_api.sh)
    롤백     -> 되돌린 커밋의 deploy/smoke.py   (rollback.sh가 git archive로 꺼내 둔다)

## 이 파일이 보는 것

1. 현재 스모크가 **현재 계약**에서 통과하고, 의미 위반을 잡는다 (약화되지 않았다).
2. 현재 스모크를 옛 계약 API에 붙이면 **실패하고**, 왜 실패했는지 짝이 틀렸다고 말한다.
3. `git archive <sha> deploy`가 그 커밋의 `smoke.py`를 실제로 내놓는다 — 롤백이 쓰는
   방법이 빈손으로 끝나지 않는다.
4. (기록이 있을 때만) **옛 스모크 + 옛 계약 API -> 통과.** 얕은 체크아웃에서는 옛
   파일을 꺼낼 수 없어 건너뛴다. 그 경우 건너뛴 이유를 명시한다.

스모크는 실제 HTTP를 쓴다. 그래서 응답을 손으로 적지 않고 **실제 앱에서 한 번 받아**
그대로 돌려주는 최소 서버에 싣는다. 계약 모양이 바뀌면 이 검사도 함께 움직인다.
"""

from __future__ import annotations

import http.server
import json
import subprocess
import sys
import threading
import urllib.parse
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.osrm import OsrmClient
from app.adapters.poi import PoiRepository
from app.service import AnalysisService
from app.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = REPO_ROOT / "deploy" / "smoke.py"
# 이 PR의 base. 되돌림 대상으로 실제로 존재하는 옛 계약이다(/route 501).
BASE_SHA = "9212bcf95fd624aff66729c1b54244ceed1d9607"

CENTER_LON = 127.14020
CENTER_LAT = 36.47130
# 입력과 **다른** 스냅 지점. 같으면 "출발지가 스냅된 곳인가"를 볼 수 없다.
ORIGIN_SNAP = (127.140777, 36.471888)
DEST_SNAP = (127.143333, 36.474444)


def _settings(gpkg: Path) -> Settings:
    return Settings(
        data_dir=gpkg.parent,
        data_version="2026Q3-cc-01",
        time_model_version="tm1",
        poi_date="2026-07-01",
        osrm_base_url="http://osrm.test",
        osrm_timeout_s=4.0,
        analysis_budget_s=5.0,
    )


def _osrm_handler(request: httpx.Request) -> httpx.Response:
    """모의 OSRM. `/table`이 고른 출발지 스냅을 `/route`가 그대로 쓰게 만든다."""
    path = request.url.path
    if path.startswith("/nearest"):
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "waypoints": [{"location": list(ORIGIN_SNAP), "distance": 12.0, "hint": "origin"}],
            },
        )
    if path.startswith("/table"):
        raw = path.split("/table/v1/foot/")[-1].split("?")[0]
        destinations = raw.split(";")[1:]
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "durations": [[240.0 + 10 * i for i in range(len(destinations))]],
                "distances": [[290.0 + 10 * i for i in range(len(destinations))]],
                "sources": [{"location": list(ORIGIN_SNAP), "hint": "origin"}],
                "destinations": [
                    {"location": list(DEST_SNAP), "hint": f"dest{i}"}
                    for i in range(len(destinations))
                ],
            },
        )
    if path.startswith("/route"):
        return httpx.Response(
            200,
            json={
                "code": "Ok",
                "routes": [
                    {
                        "duration": 540.0,
                        "distance": 702.0,
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [
                                list(ORIGIN_SNAP),
                                [127.1420, 36.4730],
                                list(DEST_SNAP),
                            ],
                        },
                    }
                ],
                "waypoints": [
                    {"location": list(ORIGIN_SNAP), "hint": "origin"},
                    {"location": list(DEST_SNAP), "hint": "dest0"},
                ],
            },
        )
    raise AssertionError(path)


@contextmanager
def _client(gpkg: Path) -> Iterator[TestClient]:
    from app import main

    settings = _settings(gpkg)
    service = AnalysisService(
        settings,
        poi=PoiRepository(gpkg),
        osrm=OsrmClient(
            "http://osrm.test",
            client=httpx.Client(transport=httpx.MockTransport(_osrm_handler)),
        ),
    )
    original_settings, original_service = main.settings, main._service  # noqa: SLF001
    main.settings, main._service = settings, service  # noqa: SLF001
    try:
        yield TestClient(main.app, raise_server_exceptions=False)
    finally:
        main.settings, main._service = original_settings, original_service  # noqa: SLF001


@pytest.fixture(scope="module")
def contract(synthetic_gpkg: Path) -> dict[str, Any]:
    """**실제 앱에서** analyze·route 응답을 한 번 받아 둔다.

    손으로 적으면 계약이 바뀌어도 이 검사가 따라오지 않는다.
    """
    with _client(synthetic_gpkg) as client:
        analyze = client.get(
            "/api/analyze", params={"lon": f"{CENTER_LON:.5f}", "lat": f"{CENTER_LAT:.5f}"}
        )
        assert analyze.status_code == 200, analyze.text
        body = analyze.json()
        fid = next(
            item["best"]["fid"]
            for item in body["nearest"]
            if item["status"] == "ok" and item["best"]
        )
        route = client.get(
            "/api/route",
            params={"lon": f"{CENTER_LON:.5f}", "lat": f"{CENTER_LAT:.5f}", "fid": str(fid)},
        )
        assert route.status_code == 200, route.text
    return {"analyze": body, "route": route.json()}


class _Release:
    """하나의 배포본을 흉내 내는 최소 서버.

    `route_status=501`이면 `/route`가 없던 옛 계약이다.
    """

    def __init__(self, contract: dict[str, Any], *, route_status: int = 200, route_body=None):
        self.analyze = contract["analyze"]
        self.route_status = route_status
        self.route = contract["route"] if route_body is None else route_body
        self._server: http.server.ThreadingHTTPServer | None = None

    def __enter__(self) -> str:
        release = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):  # 조용히
                pass

            def _json(self, status: int, payload) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/api/health":
                    self._json(200, {"status": "ok"})
                elif parsed.path == "/api/analyze":
                    self._json(200, release.analyze)
                elif parsed.path == "/api/route":
                    if release.route_status != 200:
                        self._json(release.route_status, {"detail": "not implemented"})
                    else:
                        self._json(200, release.route)
                else:
                    body = b'<!doctype html><div id="root"></div>'
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._server.server_port}"

    def __exit__(self, *exc) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()


def _coords_file(tmp_path: Path) -> Path:
    """스모크가 도는 좌표 하나. 합성 픽스처의 중심이라 분석이 실제로 답한다.

    모양은 저장소의 `deploy/smoke_coords.json`과 같다 — 옛 스모크와 현재 스모크가
    같은 파일을 읽어야 둘을 나란히 놓고 비교할 수 있다.
    """
    path = tmp_path / "coords.json"
    path.write_text(
        json.dumps(
            {
                "coords": [
                    {
                        "id": "gongju-knu-gate",
                        "label": "공주대 신관캠퍼스 정문",
                        "lon": CENTER_LON,
                        "lat": CENTER_LAT,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _run_smoke(script: Path, base_url: str, coords: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--base-url",
            base_url,
            "--coords",
            str(coords),
            "--timeout",
            "10",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=REPO_ROOT,
    )


# --- 1. 현재 계약 + 현재 스모크 ---------------------------------------------


def test_the_current_smoke_passes_on_the_current_contract(contract, tmp_path):
    """대조군. 이것이 깨지면 아래 실패들이 무엇을 뜻하는지 말할 수 없다."""
    coords = _coords_file(tmp_path)
    with _Release(contract) as base_url:
        result = _run_smoke(SMOKE, base_url, coords)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_current_smoke_still_catches_a_broken_route_origin(contract, tmp_path):
    """**의미 불변식을 약화하지 않았다.** 출발지가 분석의 snapped와 다르면 실패한다."""
    broken = json.loads(json.dumps(contract["route"]))
    broken["snapped_origin"]["lon"] = round(broken["snapped_origin"]["lon"] + 0.01, 5)
    coords = _coords_file(tmp_path)
    with _Release(contract, route_body=broken) as base_url:
        result = _run_smoke(SMOKE, base_url, coords)
    assert result.returncode != 0, "출발지가 어긋났는데 통과했다"
    assert "snapped" in result.stdout + result.stderr


# --- 2. 옛 계약 + 현재 스모크 (D3가 만든 잘못된 짝) --------------------------


def test_the_current_smoke_refuses_an_older_contract_and_says_why(contract, tmp_path):
    """옛 산출물에 현재 스모크를 붙이면 **실패하되 이유를 말한다.**

    통과시키면 안 된다 — 현재 배포본에서 /route가 501이면 그것은 진짜 결함이다.
    그래서 판정은 실패 그대로 두고, 짝이 틀렸을 가능성을 함께 적는다.
    """
    coords = _coords_file(tmp_path)
    with _Release(contract, route_status=501) as base_url:
        result = _run_smoke(SMOKE, base_url, coords)
    assert result.returncode != 0, "/route 501인데 통과했다"
    output = result.stdout + result.stderr
    assert "501" in output
    assert "smoke.py" in output and "rollback" in output, output[-800:]


# --- 3. 롤백이 쓰는 방법이 실제로 그 커밋의 스모크를 내놓는다 ----------------


def test_git_archive_yields_the_smoke_of_that_commit(tmp_path):
    """`rollback.sh`가 쓰는 `git archive <sha> deploy`가 빈손으로 끝나지 않는지.

    되돌림 대상 SHA가 아니라 **HEAD**로 본다. 얕은 체크아웃에서도 항상 있는 커밋이라
    이 검사는 어디서든 돈다. 보려는 것은 "그 방법이 smoke.py를 내놓는가"다.
    """
    archive = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "archive", "HEAD", "deploy"],
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        pytest.skip(f"git archive를 쓸 수 없다: {archive.stderr[:200]!r}")
    tar = tmp_path / "deploy.tar"
    tar.write_bytes(archive.stdout)
    subprocess.run(["tar", "-x", "-f", str(tar), "-C", str(tmp_path)], check=True)
    restored = tmp_path / "deploy" / "smoke.py"
    assert restored.is_file(), "되돌린 커밋의 deploy/에 smoke.py가 없다"
    assert "--base-url" in restored.read_text(encoding="utf-8")


# --- 4. 옛 스모크 + 옛 계약 = 통과 (기록이 있을 때만) ------------------------


def test_the_matching_old_smoke_passes_on_the_old_contract(contract, tmp_path):
    """**짝이 맞으면 정상 롤백이 정상으로 보인다.**

    옛 파일은 기록에서 꺼낸다. `api-checks`는 얕은 체크아웃이라 그 커밋이 없을 수 있고,
    그때는 건너뛴다 — 없는 것을 있는 것처럼 통과시키지 않는다. 전체 기록이 있는 곳
    (개발 PC·`fetch-depth: 0`)에서는 실제로 돈다.
    """
    show = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{BASE_SHA}:deploy/smoke.py"],
        capture_output=True,
        check=False,
    )
    if show.returncode != 0:
        pytest.skip(
            f"기록에 {BASE_SHA[:7]}가 없다(얕은 체크아웃). 옛 스모크를 꺼낼 수 없어 건너뛴다."
        )
    old_smoke = tmp_path / "old_smoke.py"
    old_smoke.write_bytes(show.stdout)
    coords = _coords_file(tmp_path)
    with _Release(contract, route_status=501) as base_url:
        result = _run_smoke(old_smoke, base_url, coords)
    assert result.returncode == 0, (
        "옛 계약 API에 그 배포본의 스모크를 썼는데 실패했다 — 롤백 검증이 불가능해진다\n"
        + result.stdout[-2000:]
        + result.stderr[-2000:]
    )
