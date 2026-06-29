#!/usr/bin/env python3
import json

from _smoke import client


def main() -> int:
    with client() as api:
        response = api.get("/integrations/probes")
        if response.status_code != 200:
            raise SystemExit(response.text)
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
