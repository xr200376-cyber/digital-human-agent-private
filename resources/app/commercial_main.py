from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse

from app.commercial_center import router as commercial_router
from app.settings import Settings, get_settings


def _docs_url() -> str | None:
    return "/docs" if os.getenv("COMMERCIAL_ENABLE_DOCS", "").lower() in {"1", "true", "yes"} else None


app = FastAPI(
    title="Xiongtu IP Agent Commercial Backend",
    version="1.0.0",
    docs_url=_docs_url(),
    redoc_url=None,
    openapi_url="/openapi.json" if _docs_url() else None,
)
app.include_router(commercial_router)


@app.on_event("startup")
def ensure_runtime_dirs() -> None:
    settings = get_settings()
    storage_dir = Path(settings.storage_dir)
    (storage_dir / "commercial_center").mkdir(parents=True, exist_ok=True)
    (storage_dir / "commercial_center" / "payment_evidence").mkdir(parents=True, exist_ok=True)
    (storage_dir / "commercial_center" / "releases").mkdir(parents=True, exist_ok=True)
    (storage_dir / "commercial_center" / "backups").mkdir(parents=True, exist_ok=True)


@app.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/admin")


@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "ok": True,
        "service": "xiongtu-commercial-backend",
        "app_env": settings.app_env,
        "storage_dir": str(settings.storage_dir),
        "commercial_repository_backend": settings.commercial_repository_backend,
        "commercial_api_base_url": settings.commercial_api_base_url,
    }
