#!/usr/bin/env python3
"""Load test for DemumuMind Panel as an LLM provider.

Usage:
    python harness/load/load_test.py \
      --base http://127.0.0.1:8000 \
      --key dm-... \
      --model z-ai/glm-5.2:free \
      --concurrency 20 --duration 30 --warmup 5 \
      --mix chat:0.6 stream:0.25 models:0.15

Measures: RPS, latency (p50/p95/p99), error rate, cache hits.
No external deps beyond httpx (already in the venv).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field

import httpx

CHAT_BODY = {
    "model": "{model}",
    "messages": [{"role": "user", "content": "Hello, tell me a one-line fact."}],
    "max_tokens": 16,
    "temperature": 0,  # cacheable
}


@dataclass
class Result:
    kind: str
    status: int
    latency_ms: float
    cached: bool = False
    error: str | None = None


@dataclass
class Stats:
    results: list[Result] = field(default_factory=list)
    start: float = 0.0
    end: float = 0.0

    def report(self) -> None:
        dur = max(self.end - self.start, 1e-9)
        total = len(self.results)
        ok = [r for r in self.results if r.status == 200]
        fail = [r for r in self.results if r.status != 200]
        lat = [r.latency_ms for r in self.results if r.status == 200]
        cached = sum(1 for r in ok if r.cached)
        by_status = Counter(r.status for r in self.results)

        def pct(q: float) -> float:
            if not lat:
                return 0.0
            return statistics.quantiles(lat, n=100, method="inclusive")[int(q) - 1]

        print("\n=== LOAD TEST SUMMARY ===")
        print(f"duration      : {dur:.1f}s")
        print(f"requests      : {total}")
        print(f"RPS           : {total / dur:.1f}")
        print(f"ok / fail     : {len(ok)} / {len(fail)}")
        print(f"status codes  : {dict(by_status)}")
        print(f"cache hits    : {cached} ({cached / max(len(ok), 1) * 100:.0f}% of ok)")
        if lat:
            print(f"latency p50   : {pct(50):.0f} ms")
            print(f"latency p95   : {pct(95):.0f} ms")
            print(f"latency p99   : {pct(99):.0f} ms")
            print(f"latency max   : {max(lat):.0f} ms")
        errs = [r.error for r in fail if r.error]
        if errs:
            print(f"sample errors : {errs[:5]}")
        print("========================")


async def do_chat(client: httpx.AsyncClient, base: str, key: str, model: str, stream: bool, prompt_idx: int = 0) -> Result:
    body = json.loads(json.dumps(CHAT_BODY).replace("{model}", model))
    # vary prompt so we hit the upstream (real generation), not only cache
    body["messages"] = [
        {"role": "user", "content": f"Question {prompt_idx}: list three planets and their moons. Answer in one line."}
    ]
    headers = {"Authorization": f"Bearer {key}"}
    t0 = time.monotonic()
    try:
        if stream:
            async with client.stream(
                "POST", f"{base}/v1/chat/completions", headers=headers, json={**body, "stream": True}
            ) as resp:
                cached = resp.headers.get("x-dm-cache") == "hit"
                await resp.aread()
                latency = (time.monotonic() - t0) * 1000
                return Result("stream", resp.status_code, latency, cached=cached)
        resp = await client.post(
            f"{base}/v1/chat/completions", headers=headers, json=body
        )
        latency = (time.monotonic() - t0) * 1000
        cached = resp.headers.get("x-dm-cache") == "hit"
        return Result("chat", resp.status_code, latency, cached=cached)
    except httpx.HTTPError as exc:
        return Result("chat" if not stream else "stream", 0, 0, error=f"{type(exc).__name__}: {str(exc)[:80]}")


async def do_models(client: httpx.AsyncClient, base: str, key: str) -> Result:
    t0 = time.monotonic()
    try:
        resp = await client.get(f"{base}/v1/models?limit=5", headers={"Authorization": f"Bearer {key}"})
        latency = (time.monotonic() - t0) * 1000
        return Result("models", resp.status_code, latency)
    except httpx.HTTPError as exc:
        return Result("models", 0, 0, error=f"{type(exc).__name__}: {str(exc)[:80]}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--key", required=True)
    ap.add_argument("--model", default="deepseek-ai/DeepSeek-V4-Flash-0731")
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--warmup", type=float, default=3.0)
    ap.add_argument("--duration", type=float, default=20.0)
    ap.add_argument("--mix", default="chat:0.6,stream:0.25,models:0.15")
    args = ap.parse_args()

    mix: list[str] = []
    for part in args.mix.split(","):
        name, _, weight = part.partition(":")
        mix.extend([name] * int(float(weight) * 10))
    if not mix:
        mix = ["chat"]

    stats = Stats()
    stop = asyncio.Event()

    print(f"Load test: base={args.base} concurrency={args.concurrency} "
          f"warmup={args.warmup}s duration={args.duration}s mix={args.mix}")
    print(f"Warming up {args.warmup}s ...")
    stats.start = time.monotonic()
    warm = asyncio.create_task(asyncio.sleep(args.warmup))
    await warm

    stats.start = time.monotonic()
    counter = 0

    async def _worker(idx: int) -> None:
        nonlocal counter
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
            while not stop.is_set():
                kind = random.choice(mix)
                counter += 1
                prompt_idx = counter % 1000
                if kind == "chat":
                    r = await do_chat(client, args.base, args.key, args.model, stream=False, prompt_idx=prompt_idx)
                elif kind == "stream":
                    r = await do_chat(client, args.base, args.key, args.model, stream=True, prompt_idx=prompt_idx)
                else:
                    r = await do_models(client, args.base, args.key)
                stats.results.append(r)

    workers = [asyncio.create_task(_worker(i)) for i in range(args.concurrency)]
    await asyncio.sleep(args.duration)
    stop.set()
    await asyncio.gather(*workers, return_exceptions=True)
    stats.end = time.monotonic()

    stats.report()


if __name__ == "__main__":
    asyncio.run(main())
