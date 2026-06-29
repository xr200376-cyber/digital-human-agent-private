import httpx

payload = {
    "brand_name": "某护肤品牌",
    "persona": "专业但亲和的护肤顾问",
    "topic": "熬夜后如何快速修护皮肤",
    "platform": "douyin",
    "duration_seconds": 45,
    "avatar_mode": "offline",
    "lip_sync_engine": "latentsync",
    "export_jianying_draft": True,
}

with httpx.Client(base_url="http://127.0.0.1:8080", timeout=60) as client:
    created = client.post("/tasks", json=payload)
    created.raise_for_status()
    task = created.json()
    print("created", task)

    run = client.post(f"/tasks/{task['task_id']}/run")
    run.raise_for_status()
    print("result", run.json())
