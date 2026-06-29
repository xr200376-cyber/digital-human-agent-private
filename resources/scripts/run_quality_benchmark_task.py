#!/usr/bin/env python3
from pathlib import Path

from _smoke import _raise_for_status, client


def main() -> int:
    with client() as api:
        report = api.post("/quality/benchmarks/run", json={})
        _raise_for_status(report)
        body = report.json()
        benchmark_id = body["benchmark_id"]
        scenarios = {row["scenario"] for row in body["scenarios"]}
        expected = {"30s_task", "60s_task", "batch_10_task"}
        if scenarios != expected:
            raise SystemExit(f"unexpected scenarios: {sorted(scenarios)}")
        task_count = sum(len(row["task_ids"]) for row in body["scenarios"])
        if task_count != 12:
            raise SystemExit(f"unexpected benchmark task count: {task_count}")

        dashboard = api.get("/quality/dashboard")
        _raise_for_status(dashboard)

        download = api.get(f"/quality/benchmarks/{benchmark_id}/download.json")
        _raise_for_status(download)
        out_path = Path("storage") / "quality_benchmark_report.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(download.content)

        print(f"benchmark_id={benchmark_id}")
        print(f"scenarios={','.join(sorted(scenarios))}")
        print(f"task_count={task_count}")
        print(f"report={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
