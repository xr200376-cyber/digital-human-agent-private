#!/usr/bin/env python3
from _smoke import client


def main() -> int:
    with client() as api:
        health = api.get("/health")
        readiness = api.get("/readiness")
        if health.status_code != 200 or readiness.status_code != 200:
            raise SystemExit("governance smoke failed")
        print("governance_smoke=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
