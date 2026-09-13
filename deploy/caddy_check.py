"""실제 Caddy로 로그 정제와 자산 전환을 확인한다 (v2.4 5절, 4-1).

`api/tests/test_caddy_log_redaction.py`는 **설정 파일의 구조만** 본다. 그것으로는
"이 정규식이 실제 요청에서 무엇을 남기는가"를 알 수 없고, `caddy validate`도 잡지
못한다 — 두 설정 모두 유효하기 때문이다. 실제로 Astra 독립감사가 찾은 두 결함이
바로 그 틈에 있었다.

  finding 3  `/%70/36.47130,127.14020`(= `/p/...`의 퍼센트 인코딩)이 Caddy에서는 같은
             요청으로 처리되는데 **접근 로그에는 좌표가 그대로** 남았다.
  finding 9  배포 전환 순간, 이미 받은 HTML이 가리키는 직전 배포본의 자산이 404였다.

그래서 이 스크립트는 저장소의 `deploy/Caddyfile`을 **그대로** 컨테이너에 넣고 실제
요청을 보낸 뒤 로그를 읽는다. 대조군(정상 경로)과 반례(인코딩·malformed·쿼리·Referer)를
같은 실행에서 함께 돌려, 필터가 아무것도 하지 않는 상태가 통과로 보이지 않게 한다.

바꾸는 것은 두 줄뿐이다 — 사이트 주소(도메인 → :PORT)와 `/api/*` 프록시 대상(오류
로그 경로를 만들려고 일부러 닫힌 포트). **로그 설정과 handle 블록은 손대지 않는다.**

  python deploy/caddy_check.py            # 도커로 caddy:2.11.4-alpine 실행
  python deploy/caddy_check.py --keep     # 실패했을 때 로그 원문을 남긴다

CI는 도커 안에서 도커를 띄우지 않으므로 이 검사는 **개발 PC에서** 돌린다. 결과는
PR 본문과 README에 기록한다.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

# 개발 PC 콘솔이 cp949라 한국어와 em dash를 그대로 찍지 못한다. 출력만 UTF-8로 고정한다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
CADDYFILE = REPO_ROOT / "deploy" / "Caddyfile"

# api/tests/test_deployment_pins.py가 이 태그를 compose.yaml과 맞춰 고정한다.
CADDY_IMAGE = "caddy:2.11.4-alpine"
PORT = 8931
CONTAINER = "geoleobom-caddy-check"

# 로그에 남으면 안 되는 값. 실제 좌표·검색어와 같은 모양으로 둔다.
LAT, LON = "36.47130", "127.14020"
SECRET_QUERY = "공주대학교신관캠퍼스"
# 요청 줄은 ASCII다. 브라우저가 보내는 것과 같은 퍼센트 인코딩 형태로 나간다.
SECRET_QUERY_ENCODED = urllib.parse.quote(SECRET_QUERY)
# `/assets/` 뒤에 실어 보내는 표식. 파일명 글자 집합([A-Za-z0-9._-]) 안에 있으면서
# 사람이 정한 문자열이라, "파일명처럼 생겼다"가 안전의 근거가 아님을 보여 준다
# (Astra delta D1의 반례를 그대로 쓴다).
ASSET_PROBE = "AUDIT_PRIVATE_QUERY"
# 로그에는 인코딩된 모양으로 남을 것이므로 **둘 다** 없는지 본다.
SECRETS = (LAT, LON, SECRET_QUERY, SECRET_QUERY_ENCODED, ASSET_PROBE)

# 자산 이름은 내용 해시라 민감값이 아니다. 전환 검사에서 이름으로 구분한다.
OLD_ASSET = "index-OLDoldOLD.js"
NEW_ASSET = "index-NEWnewNEW.js"


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, capture_output=True, text=True, check=check, encoding="utf-8"
    )


def _site_config() -> str:
    """저장소 Caddyfile에서 **주소와 프록시 대상만** 바꾼다.

    로그 스니펫·handle 블록·헤더는 그대로 둔다. 그것이 검사 대상이기 때문이다.
    """
    text = CADDYFILE.read_text(encoding="utf-8")
    if "geoleobom.kr {" not in text:
        raise SystemExit("Caddyfile에서 사이트 블록을 찾지 못했다")
    text = text.replace("geoleobom.kr {", f":{PORT} {{", 1)
    # 오류 로그 경로를 만들려고 닫힌 포트로 보낸다. reverse_proxy 실패는 전역 기본
    # 로거로 나가며, 5절은 **그쪽도** 정제하라고 정했다.
    text = text.replace("reverse_proxy api:8000", "reverse_proxy 127.0.0.1:9", 1)
    return text


def _web_root(base: Path) -> None:
    """current/previous 두 배포본을 만든다. 자산 이름이 서로 다르다."""
    for name, asset in (("previous", OLD_ASSET), ("current", NEW_ASSET)):
        release = base / name
        (release / "assets").mkdir(parents=True)
        (release / "assets" / asset).write_text(f"// {name}\n", encoding="utf-8")
        (release / "index.html").write_text(
            f'<!doctype html><html><body><div id="root"></div>'
            f'<script type="module" src="/assets/{asset}"></script></body></html>',
            encoding="utf-8",
        )


def _request(path: str, *, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    """`path`를 **그대로** 보낸다. 라이브러리가 퍼센트 인코딩을 정규화하면 안 된다."""
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    try:
        conn.putrequest("GET", path, skip_host=False, skip_accept_encoding=True)
        for key, value in (headers or {}).items():
            conn.putheader(key, value)
        conn.endheaders()
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def _logs() -> str:
    result = _run("docker", "logs", CONTAINER, check=False)
    return result.stdout + result.stderr


def _uris(logs: str) -> list[str]:
    """기록된 `request.uri` 값들. 접근 로그와 오류 로그 양쪽에서 모은다."""
    found: list[str] = []
    for line in logs.splitlines():
        if '"uri"' not in line:
            continue
        for match in re.finditer(r'"uri"\s*:\s*"((?:[^"\\]|\\.)*)"', line):
            found.append(json.loads(f'"{match.group(1)}"'))
    return found


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.count = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.count += 1
        print(f"{'PASS' if ok else 'FAIL'} {name}{f' — {detail}' if detail else ''}")
        if not ok:
            self.failures.append(f"{name}: {detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="실제 Caddy 로그 정제·자산 전환 확인")
    parser.add_argument(
        "--keep", action="store_true", help="실패해도 컨테이너를 남긴다"
    )
    args = parser.parse_args(argv)

    if shutil.which("docker") is None:
        print("docker가 없다. 이 검사는 개발 PC에서 돈다.", file=sys.stderr)
        return 2

    report = Report()
    workdir = Path(tempfile.mkdtemp(prefix="caddy-check-"))
    try:
        (workdir / "Caddyfile").write_text(_site_config(), encoding="utf-8")
        web = workdir / "web"
        web.mkdir()
        _web_root(web)

        _run("docker", "rm", "-f", CONTAINER, check=False)
        _run(
            "docker",
            "run",
            "-d",
            "--name",
            CONTAINER,
            "-p",
            f"127.0.0.1:{PORT}:{PORT}",
            "-v",
            f"{workdir / 'Caddyfile'}:/etc/caddy/Caddyfile:ro",
            "-v",
            f"{web}:/srv/web:ro",
            CADDY_IMAGE,
            "caddy",
            "run",
            "--config",
            "/etc/caddy/Caddyfile",
            "--adapter",
            "caddyfile",
        )

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                _request("/")
                break
            except OSError:
                time.sleep(0.4)
        else:
            print(_logs(), file=sys.stderr)
            raise SystemExit("Caddy가 뜨지 않았다")

        # --- 1. 로그 정제: 대조군과 반례를 같은 실행에서 -----------------------
        #
        # 정상 `/p`는 예전에도 정제됐다. 여기서 새로 보는 것은 그 밖의 모양들이다.
        probes = [
            ("정상 /p", f"/p/{LAT},{LON}", None),
            ("퍼센트 인코딩 /%70", f"/%70/{LAT},{LON}", None),
            ("대문자 /P", f"/P/{LAT},{LON}", None),
            ("중복 슬래시 //p", f"//p/{LAT},{LON}", None),
            ("경로 순회 표기", f"/assets/../p/{LAT},{LON}", None),
            ("인코딩된 슬래시", f"/p%2F{LAT},{LON}", None),
            ("쿼리 문자열(analyze)", f"/api/analyze?lon={LON}&lat={LAT}", None),
            ("쿼리 문자열(search)", f"/api/search?q={SECRET_QUERY_ENCODED}", None),
            ("비교 URL 쿼리", f"/c?p={LAT},{LON}&p=36.4,127.1", None),
            ("알 수 없는 경로", f"/../../{LAT},{LON}", None),
            # Astra delta D1: `/assets/` 뒤 문자열도 **요청자가 정한다.** 파일이 없어
            # 404여도 로그에는 남았다. 글자 집합이 파일명처럼 생겼다는 것은 출처의
            # 증거가 아니다 — 좌표도 검색어도 그 집합에 들어간다.
            ("자산 경로에 좌표", f"/assets/{LAT}-{LON}.js", None),
            ("자산 경로에 문장", f"/assets/{ASSET_PROBE}.js", None),
            ("자산 경로에 쉼표 좌표", f"/assets/{LAT},{LON}", None),
            ("자산 하위 경로", f"/assets/sub/{LAT}-{LON}.js", None),
            ("자산 경로 인코딩", f"/assets/%2e%2e/{LAT},{LON}", None),
            ("정상 해시 자산(대조군)", f"/assets/{NEW_ASSET}", None),
            (
                "Referer 헤더",
                "/api/health",
                {"Referer": f"https://geoleobom.kr/p/{LAT},{LON}"},
            ),
        ]
        for _, path, headers in probes:
            try:
                _request(path, headers=headers)
            except OSError as exc:  # 서버가 끊어도 로그는 남는다
                print(f"  (요청 중 끊김: {path} {exc})")

        time.sleep(1.0)
        logs = _logs()
        uris = _uris(logs)

        report.check(
            "로그에 request.uri가 실제로 기록됐다",
            len(uris) >= len(probes),
            f"{len(uris)}건",
        )
        for secret in SECRETS:
            leaking = [uri for uri in uris if secret in uri]
            report.check(
                f"기록된 uri 어디에도 '{secret}'가 없다",
                not leaking,
                "; ".join(leaking[:3]),
            )
        # 헤더는 통째로 지우므로 Referer는 아예 없어야 한다.
        report.check(
            "로그에 요청 헤더가 남지 않는다(Referer 포함)",
            '"headers"' not in logs and "Referer" not in logs,
            "headers 필드가 남아 있다",
        )
        # 정제가 **아무것도 남기지 않는 상태**도 통과로 보이면 안 된다.
        report.check(
            "허용 목록의 경로 템플릿은 그대로 남는다",
            "/api/analyze" in uris
            and "/api/search" in uris
            and "/p" in uris
            and "/c" in uris
            and "/assets" in uris,
            f"기록된 값: {sorted(set(uris))[:12]}",
        )
        # 자산은 **템플릿 한 덩어리**로만 남는다. 파일명이 붙어 있으면 안 된다.
        asset_uris = [uri for uri in uris if uri.startswith("/assets")]
        report.check(
            "자산 요청은 '/assets'로만 기록된다(파일명 없음)",
            bool(asset_uris) and all(uri == "/assets" for uri in asset_uris),
            f"기록된 값: {sorted(set(asset_uris))[:6]}",
        )

        # --- 2. 자산 전환 (finding 9) -----------------------------------------
        #
        # current = 새 배포본, previous = 직전 배포본. 이미 받은 HTML이 가리키는
        # 직전 자산이 전환 뒤에도 열려야 한다.
        status_new, _ = _request(f"/assets/{NEW_ASSET}")
        report.check("현재 배포본 자산 200", status_new == 200, str(status_new))
        status_old, body_old = _request(f"/assets/{OLD_ASSET}")
        report.check(
            "전환 직전 배포본 자산도 200 (열어 둔 탭이 깨지지 않는다)",
            status_old == 200,
            str(status_old),
        )
        report.check(
            "직전 자산의 내용이 직전 배포본의 것이다",
            b"previous" in body_old,
            body_old[:40].decode("utf-8", "replace"),
        )
        status_missing, _ = _request("/assets/index-NEVERexisted.js")
        report.check(
            "둘 다에 없는 자산은 여전히 404 (대조군)",
            status_missing == 404,
            str(status_missing),
        )
        status_page, body_page = _request(f"/p/{LAT},{LON}")
        report.check(
            "공유 URL은 SPA fallback으로 200",
            status_page == 200 and b'<div id="root">' in body_page,
            str(status_page),
        )
    finally:
        if not args.keep:
            _run("docker", "rm", "-f", CONTAINER, check=False)
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            print(f"\n남긴 것: 컨테이너 {CONTAINER}, 작업 디렉터리 {workdir}")

    print(f"\n{report.count}건 중 실패 {len(report.failures)}건")
    for failure in report.failures:
        print(f"  - {failure}", file=sys.stderr)
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
