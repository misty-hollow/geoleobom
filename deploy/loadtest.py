"""부하·응답시간 측정 (v2.3 10절 게이트 2 '성능·자원').

게이트 2가 요구하는 네 가지를 잰다.

1. **캐시 미스 대표 5지점 2초 목표 실측** — `--mode latency`.
2. **최대 후보(160 목적지) × 동시 4요청 부하에서 오류·OOM·지속적 스왑 I/O 없음** —
   `--mode load --concurrency 4`.
3. **부하 중 `MemAvailable` 약 1GB 이상** — 서버에서 `deploy/sample_memory.sh`를
   1초 간격으로 돌려 최솟값을 기록한다. 이 스크립트는 클라이언트 쪽만 잰다.
4. **한국 내 클라이언트 응답시간** — 이 스크립트를 개발 PC(한국)에서 돌린 값이
   클라이언트 체감 시간이다. 서버 내부 처리 시간은 API 로그의 `duration_ms`로
   따로 읽는다. 게이트 2는 둘을 **구분해 적으라고** 정했다.

**캐시 미스를 어떻게 보장하는가.** 캐시 키는 `analyze:{data_version}:{time_model_version}:
{lon}:{lat}`이고 좌표는 5자리 문자열 그대로다(4-3 2단계, 격자 반올림 없음). 그래서
5번째 자리만 바꾸면(약 1m) 후보 집합은 사실상 그대로인 채 키가 달라진다. 매 요청마다
새 오프셋을 쓰므로 같은 좌표를 두 번 보내지 않는다.

표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_COORDS = Path(__file__).resolve().parent / "smoke_coords.json"

# 5번째 소수 자리 = 약 1.1m. 캐시 키만 바꾸고 후보 집합은 바꾸지 않는 크기다.
FIFTH_DECIMAL = 0.00001


@dataclass
class Sample:
    spot: str
    status: int
    ms: float
    cache_key_lon: float
    cache_key_lat: float
    density_status: str | None = None
    batches_hint: int | None = None
    error: str | None = None


@dataclass
class Collector:
    samples: list[Sample] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, sample: Sample) -> None:
        with self.lock:
            self.samples.append(sample)


def request_once(
    base_url: str, lon: float, lat: float, timeout_s: float, spot: str
) -> Sample:
    query = urllib.parse.urlencode({"lon": f"{lon:.5f}", "lat": f"{lat:.5f}"})
    url = f"{base_url.rstrip('/')}/api/analyze?{query}"
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
        elapsed = (time.perf_counter() - started) * 1000.0
        density = body.get("density", {})
        return Sample(
            spot=spot,
            status=200,
            ms=elapsed,
            cache_key_lon=round(lon, 5),
            cache_key_lat=round(lat, 5),
            density_status=density.get("status"),
            batches_hint=density.get("candidates_checked"),
        )
    except urllib.error.HTTPError as exc:
        return Sample(
            spot=spot,
            status=exc.code,
            ms=(time.perf_counter() - started) * 1000.0,
            cache_key_lon=round(lon, 5),
            cache_key_lat=round(lat, 5),
            error=exc.read().decode("utf-8", "replace")[:200],
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return Sample(
            spot=spot,
            status=0,
            ms=(time.perf_counter() - started) * 1000.0,
            cache_key_lon=round(lon, 5),
            cache_key_lat=round(lat, 5),
            error=str(exc)[:200],
        )


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


def report(collector: Collector, label: str) -> int:
    samples = collector.samples
    ok = [s for s in samples if s.status == 200]
    bad = [s for s in samples if s.status != 200]
    times = [s.ms for s in ok]

    print(f"\n== {label}")
    print(f"요청 {len(samples)}건 · 성공 {len(ok)} · 실패 {len(bad)}")
    if times:
        print(
            f"클라이언트 체감(ms)  최소 {min(times):.0f} · 중앙 {statistics.median(times):.0f} · "
            f"p95 {percentile(times, 0.95):.0f} · 최대 {max(times):.0f}"
        )
    by_density: dict[str, int] = {}
    for sample in ok:
        key = sample.density_status or "?"
        by_density[key] = by_density.get(key, 0) + 1
    if by_density:
        print(f"density 상태 분포: {by_density}")
    for sample in bad[:10]:
        print(f"  실패 {sample.spot} status={sample.status} {sample.error}")

    # 캐시 미스였는지: 같은 좌표를 두 번 보내지 않았는가.
    keys = {(s.cache_key_lon, s.cache_key_lat) for s in samples}
    print(f"서로 다른 캐시 키 {len(keys)} / 요청 {len(samples)}")
    if len(keys) != len(samples):
        print("  경고: 같은 좌표가 반복됐다. 일부는 캐시 히트였을 수 있다.")

    return 0 if not bad else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="부하·응답시간 측정")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--coords", type=Path, default=DEFAULT_COORDS)
    parser.add_argument("--mode", choices=("latency", "load"), default="latency")
    parser.add_argument(
        "--concurrency", type=int, default=4, help="동시 요청 수 (게이트 2 기준은 4)"
    )
    parser.add_argument("--rounds", type=int, default=1, help="좌표당 반복 라운드")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--out", type=Path, help="원자료 JSON 저장 경로")
    args = parser.parse_args(argv)

    coords = json.loads(args.coords.read_text(encoding="utf-8"))["coords"]
    collector = Collector()

    # 요청마다 5번째 자리를 다르게 줘서 캐시 미스를 보장한다.
    jobs: list[tuple[str, float, float]] = []
    for round_index in range(args.rounds):
        for offset, coord in enumerate(coords):
            shift = (round_index * len(coords) + offset + 1) * FIFTH_DECIMAL
            jobs.append(
                (str(coord["id"]), float(coord["lon"]) + shift, float(coord["lat"]))
            )

    if args.mode == "latency":
        # 순차 실행. 한 요청이 혼자 돌 때의 시간을 잰다.
        for spot, lon, lat in jobs:
            sample = request_once(args.base_url, lon, lat, args.timeout, spot)
            collector.add(sample)
            print(
                f"{spot:28s} {sample.status} {sample.ms:8.0f}ms "
                f"density={sample.density_status} checked={sample.batches_hint}"
            )
        exit_code = report(
            collector, "캐시 미스 단일 요청 응답시간 (한국 내 클라이언트)"
        )
    else:
        # 동시 N요청을 유지하며 전체 작업을 소화한다.
        queue = list(jobs)
        queue_lock = threading.Lock()

        def worker() -> None:
            while True:
                with queue_lock:
                    if not queue:
                        return
                    spot, lon, lat = queue.pop()
                collector.add(request_once(args.base_url, lon, lat, args.timeout, spot))

        started = time.perf_counter()
        threads = [threading.Thread(target=worker) for _ in range(args.concurrency)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        wall = time.perf_counter() - started
        exit_code = report(
            collector,
            f"동시 {args.concurrency}요청 부하 (총 {wall:.1f}s, 한국 내 클라이언트)",
        )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(
                [vars(s) for s in collector.samples], ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        print(f"원자료 저장: {args.out}")

    if exit_code:
        print(
            "\n실패한 요청이 있다. 게이트 2의 '오류 없음' 기준을 통과하지 못했다.",
            file=sys.stderr,
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
