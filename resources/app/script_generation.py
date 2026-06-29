from pathlib import Path

from app.adapters.base import AdapterError, ScriptGeneratorAdapter
from app.adapters.llm import OpenAICompatibleAdapter
from app.adapters.pixelle import PixelleAdapter
from app.schemas import CreateVideoTaskRequest
from app.settings import Settings


class UnconfiguredScriptGeneratorAdapter(ScriptGeneratorAdapter):
    name = "unconfigured_script_generator"

    def available(self) -> bool:
        return False

    async def generate_script(self, request: CreateVideoTaskRequest, out_dir: Path) -> Path:
        raise AdapterError(
            "real script generation is not configured: enable an OpenAI-compatible model gateway or Pixelle HTTP"
        )


def select_script_generator_adapter(settings: Settings):
    engine = (settings.llm_engine or "").lower().strip()
    if settings.dry_run:
        return PixelleAdapter(
            settings.pixelle_base_url,
            dry_run=True,
            script_endpoint=settings.pixelle_script_endpoint,
            video_endpoint=settings.pixelle_video_endpoint,
        )
    if not settings.dry_run and engine == "openai_compatible":
        return OpenAICompatibleAdapter(
            dry_run=settings.dry_run,
            enabled=settings.openai_compatible_enabled,
            base_url=settings.openai_compatible_base_url,
            api_key=settings.openai_compatible_api_key,
            model=settings.openai_compatible_model,
        )
    if settings.pixelle_enabled:
        return PixelleAdapter(
            settings.pixelle_base_url,
            dry_run=False,
            script_endpoint=settings.pixelle_script_endpoint,
            video_endpoint=settings.pixelle_video_endpoint,
        )
    return UnconfiguredScriptGeneratorAdapter(dry_run=False)
