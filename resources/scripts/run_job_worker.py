#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.job_queue import LocalJobQueue  # noqa: E402
from app.settings import get_settings  # noqa: E402


async def run_once() -> int:
    queue = LocalJobQueue(get_settings())
    try:
        job = await queue.run_next()
    except KeyError:
        print("no queued jobs")
        return 0
    print(f"job_id={job.job_id}")
    print(f"kind={job.kind}")
    print(f"status={job.status}")
    if job.error:
        print(f"error={job.error}")
    return 0 if job.status.value == "succeeded" else 1


async def run_loop(*, interval_seconds: float) -> int:
    while True:
        await run_once()
        await asyncio.sleep(interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Sprint 21 job worker.")
    parser.add_argument("--once", action="store_true", help="process at most one queued job and exit")
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.once:
        return asyncio.run(run_once())
    try:
        return asyncio.run(run_loop(interval_seconds=args.interval_seconds))
    except KeyboardInterrupt:
        print("worker stopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
