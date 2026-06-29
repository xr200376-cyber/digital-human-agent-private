from dataclasses import dataclass

from app.schemas import RenderProfileName


@dataclass(frozen=True)
class RenderProfile:
    name: str
    width: int
    height: int
    fps: int
    avatar_engines: tuple[str, ...]
    lip_sync_engines: tuple[str, ...]
    max_retries: int
    validate_outputs: bool = True


PROFILES: dict[str, RenderProfile] = {
    "preview": RenderProfile(
        name="preview",
        width=540,
        height=960,
        fps=25,
        avatar_engines=("liveportrait", "static"),
        lip_sync_engines=("musetalk", "none"),
        max_retries=1,
    ),
    "standard": RenderProfile(
        name="standard",
        width=1080,
        height=1920,
        fps=25,
        avatar_engines=("liveportrait", "sadtalker", "static"),
        lip_sync_engines=("latentsync", "musetalk", "none"),
        max_retries=2,
    ),
    "final": RenderProfile(
        name="final",
        width=1080,
        height=1920,
        fps=30,
        avatar_engines=("duix_http", "liveportrait", "sadtalker", "static"),
        lip_sync_engines=("latentsync", "musetalk", "none"),
        max_retries=2,
    ),
    "batch": RenderProfile(
        name="batch",
        width=720,
        height=1280,
        fps=25,
        avatar_engines=("liveportrait", "static"),
        lip_sync_engines=("musetalk", "none"),
        max_retries=1,
    ),
    "compat": RenderProfile(
        name="compat",
        width=1080,
        height=1920,
        fps=25,
        avatar_engines=("role_model", "static"),
        lip_sync_engines=("yywav2lip", "wav2lip", "none"),
        max_retries=1,
    ),
}


def get_render_profile(name: str | RenderProfileName) -> RenderProfile:
    key = str(name.value if isinstance(name, RenderProfileName) else name)
    if key not in PROFILES:
        raise KeyError(f"unknown render profile: {name}")
    return PROFILES[key]
