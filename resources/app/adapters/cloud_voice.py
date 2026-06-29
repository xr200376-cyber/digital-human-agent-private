from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import httpx

from app.adapters.base import AdapterError
from app.adapters.tts import BaseTTSAdapter, TTSResult, _script_text_and_segments, _voice_options
from app.cloud_providers import (
    ALIYUN_VOICE_CLONE_SETUP_USD,
    ALIYUN_VOICE_SYNTHESIS_USD_PER_1K_CHARS,
)
from app.schemas import VoiceProfile
from app.utils.files import ensure_dir, read_json, write_json, write_placeholder_binary, write_text


class BaseCloudVoiceAdapter(BaseTTSAdapter):
    name = "cloud_voice"

    async def create_voice_clone(
        self,
        *,
        sample_audio_path: Path,
        voice_name: str,
        out_dir: Path,
        sample_audio_url: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def synthesize_with_cloned_voice(
        self,
        *,
        text: str,
        voice_id: str,
        out_dir: Path,
        script_json: Path | None = None,
        voice_profile: VoiceProfile | None = None,
    ) -> TTSResult:
        raise NotImplementedError

    async def get_voice_status(self, *, voice_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def estimate_cost(self, *, chinese_chars: int, create_clone: bool = False) -> dict[str, Any]:
        raise NotImplementedError


class AliyunBailianVoiceAdapter(BaseCloudVoiceAdapter):
    name = "aliyun_bailian"

    def __init__(
        self,
        *,
        provider_id: str = "aliyun_bailian_cosyvoice",
        dry_run: bool = True,
        api_key: str | None = None,
        region: str = "cn-beijing",
        model: str = "cosyvoice-v1",
        timeout_seconds: float = 120.0,
    ):
        self.provider_id = provider_id
        self.dry_run = dry_run
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.region = region or os.getenv("ALIYUN_BAILIAN_REGION", "cn-beijing")
        self.model = model or os.getenv("ALIYUN_VOICE_MODEL", "cosyvoice-v1")
        self.timeout_seconds = timeout_seconds
        self.base_url = "https://dashscope.aliyuncs.com/api/v1"

    def available(self) -> bool:
        if self.dry_run:
            return True
        return bool(self.api_key and self.model)

    def readiness(self) -> dict[str, Any]:
        blocking_items: list[str] = []
        if not self.dry_run and not self.api_key:
            blocking_items.append("DASHSCOPE_API_KEY")
        if not self.model:
            blocking_items.append("ALIYUN_VOICE_MODEL")
        return {
            "provider": self.provider_id,
            "ready": not blocking_items or self.dry_run,
            "dry_run": self.dry_run,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_configured": bool(self.api_key),
            "blocking_items": blocking_items,
        }

    def require_available(self) -> None:
        if self.available():
            return
        blockers = ", ".join(self.readiness()["blocking_items"])
        raise AdapterError(f"Aliyun Bailian voice adapter unavailable: {blockers}")

    async def synthesize(self, *, script_json: Path, voice_profile: VoiceProfile, out_dir: Path) -> TTSResult:
        data = read_json(script_json)
        text, _segments = _script_text_and_segments(data)
        metadata = voice_profile.metadata if isinstance(voice_profile.metadata, dict) else {}
        voice_id = str(metadata.get("cloud_voice_id") or metadata.get("provider_voice_id") or metadata.get("voice_id") or voice_profile.voice_profile_id)
        return await self.synthesize_with_cloned_voice(
            text=text,
            voice_id=voice_id,
            out_dir=out_dir,
            script_json=script_json,
            voice_profile=voice_profile,
        )

    async def create_voice_clone(
        self,
        *,
        sample_audio_path: Path,
        voice_name: str,
        out_dir: Path,
        sample_audio_url: str | None = None,
    ) -> dict[str, Any]:
        ensure_dir(out_dir)
        endpoint = _dashscope_endpoint("/services/audio/tts/customization")
        request_path = write_json(
            out_dir / "aliyun_voice_clone_request.json",
            {
                "provider": self.provider_id,
                "endpoint": endpoint,
                "model": self.model,
                "voice_name": voice_name,
                "sample_audio_path": str(sample_audio_path),
                "sample_audio_url": sample_audio_url,
                "dry_run": self.dry_run,
            },
        )
        if self.dry_run:
            response = {
                "provider": self.provider_id,
                "status": "ready",
                "voice_id": f"dryrun_{_safe_voice_prefix(voice_name)}",
                "request_log": str(request_path),
                "dry_run": True,
            }
            write_json(out_dir / "aliyun_voice_clone_response.json", response)
            return response

        self.require_available()
        if not _is_public_url(sample_audio_url):
            raise AdapterError(
                "DashScope voice clone requires sample_audio_url as a public http(s) URL; "
                "upload clean_voice_sample.wav to approved object storage first."
            )

        payload = {
            "model": "voice-enrollment",
            "input": {
                "action": "create_voice",
                "target_model": self.model,
                "prefix": _safe_voice_prefix(voice_name),
                "url": sample_audio_url,
                "language_hints": ["zh"],
            },
        }
        response_path = out_dir / "aliyun_voice_clone_response.json"
        http_log = out_dir / "aliyun_voice_clone_http.log"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            data = _safe_response_json(response)
            write_json(response_path, data)
            if response.status_code >= 400:
                raise AdapterError(f"DashScope voice clone request failed: HTTP {response.status_code}")
            voice_id = _extract_voice_id(data)
            if not voice_id:
                raise AdapterError(f"DashScope voice clone response missing voice_id: {data}")
            return {
                "provider": self.provider_id,
                "status": "ready",
                "voice_id": voice_id,
                "request_log": str(request_path),
                "response_log": str(response_path),
                "raw_response": data,
            }
        except AdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - cloud failure should surface in task step.
            write_text(http_log, f"DashScope voice clone request failed: {exc}\n")
            raise AdapterError(f"DashScope voice clone request failed: {exc}") from exc

    async def synthesize_with_cloned_voice(
        self,
        *,
        text: str,
        voice_id: str,
        out_dir: Path,
        script_json: Path | None = None,
        voice_profile: VoiceProfile | None = None,
    ) -> TTSResult:
        ensure_dir(out_dir)
        audio_path = out_dir / "voice.wav"
        segments_path = out_dir / "voice_segments.json"
        metadata_path = out_dir / "voice_metadata.json"
        endpoint = _dashscope_endpoint("/services/audio/tts/SpeechSynthesizer")
        voice_options = _voice_options(read_json(script_json) if script_json else {})
        request_path = write_json(
            out_dir / "aliyun_tts_request.json",
            {
                "provider": self.provider_id,
                "endpoint": endpoint,
                "base_url": self.base_url,
                "model": self.model,
                "voice_id": voice_id,
                "text_length": len(text),
                "script_json": str(script_json) if script_json else None,
                "voice_style": voice_options["voice_style"],
                "speech_rate": voice_options["speech_rate"],
                "dry_run": self.dry_run,
            },
        )

        if self.dry_run:
            write_placeholder_binary(audio_path, f"aliyun-cloud-voice={voice_id}")
            readable = False
            reason = "dry-run placeholder audio; Aliyun Bailian was not called"
        else:
            self.require_available()
            response_path = out_dir / "aliyun_tts_response.json"
            http_log = out_dir / "aliyun_tts_http.log"
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                    response = await client.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "input": {"text": text, "voice": voice_id},
                            "parameters": {"format": "wav"},
                        },
                    )
                    data = _safe_response_json(response)
                    write_json(response_path, data)
                    if response.status_code >= 400:
                        if _should_try_dashscope_sdk(data):
                            audio_path.write_bytes(
                                _synthesize_with_dashscope_sdk(
                                    api_key=self.api_key,
                                    model=self.model,
                                    voice_id=voice_id,
                                    text=text,
                                )
                            )
                            readable = True
                            reason = "generated by DashScope SDK websocket fallback"
                        else:
                            raise AdapterError(f"DashScope TTS request failed: HTTP {response.status_code}")
                    else:
                        audio_url = _extract_audio_url(data)
                        audio_bytes = _extract_audio_bytes(data)
                        if audio_url:
                            download = await client.get(audio_url)
                            if download.status_code >= 400:
                                raise AdapterError(f"DashScope audio download failed: HTTP {download.status_code}")
                            audio_path.write_bytes(download.content)
                            readable = True
                            reason = f"downloaded from {audio_url}"
                        elif audio_bytes:
                            audio_path.write_bytes(audio_bytes)
                            readable = True
                            reason = "decoded inline audio bytes from DashScope response"
                        else:
                            raise AdapterError(f"DashScope TTS response missing audio url/data: {data}")
            except AdapterError:
                raise
            except Exception as exc:  # noqa: BLE001 - cloud failure should surface in task step.
                write_text(http_log, f"DashScope TTS request failed: {exc}\n")
                raise AdapterError(f"DashScope TTS request failed: {exc}") from exc

        write_json(
            segments_path,
            {
                "voice_profile_id": voice_profile.voice_profile_id if voice_profile else None,
                "engine": self.provider_id,
                "voice_id": voice_id,
                "segments": [{"start": 0, "end": max(3, len(text) // 12), "text": text}],
            },
        )
        write_json(
            metadata_path,
            {
                "engine": self.provider_id,
                "voice_profile_id": voice_profile.voice_profile_id if voice_profile else None,
                "voice_source_type": getattr(voice_profile, "voice_source_type", "cloud_clone"),
                "voice_id": voice_id,
                "script_json": str(script_json) if script_json else None,
                "voice_style": voice_options["voice_style"],
                "speech_rate": voice_options["speech_rate"],
                "request_log": str(request_path),
                "readable": readable,
                "reason": reason,
            },
        )
        return TTSResult(audio_path=audio_path, segments_path=segments_path, metadata_path=metadata_path)

    async def get_voice_status(self, *, voice_id: str) -> dict[str, Any]:
        if self.dry_run:
            return {"provider": self.provider_id, "voice_id": voice_id, "status": "ready", "dry_run": True}
        self.require_available()
        return {
            "provider": self.provider_id,
            "voice_id": voice_id,
            "status": "unknown",
            "message": "Status mapping depends on the enabled DashScope voice-clone capability.",
        }

    def estimate_cost(self, *, chinese_chars: int, create_clone: bool = False) -> dict[str, Any]:
        chars = max(0, int(chinese_chars))
        setup = ALIYUN_VOICE_CLONE_SETUP_USD if create_clone else 0.0
        synthesis = round((chars / 1000.0) * ALIYUN_VOICE_SYNTHESIS_USD_PER_1K_CHARS + 1e-9, 4)
        return {
            "provider_id": self.provider_id,
            "voice_clone_setup_cost": round(setup, 2),
            "voice_synthesis_cost": synthesis,
            "estimated_total": round(setup + synthesis, 2),
            "currency": "USD",
            "warning": "Engineering estimate only; use the actual Aliyun bill as source of truth.",
        }


def _dashscope_endpoint(path: str) -> str:
    suffix = path if path.startswith("/") else f"/{path}"
    return f"https://dashscope.aliyuncs.com/api/v1{suffix}"


def _is_public_url(value: str | None) -> bool:
    lowered = str(value or "").strip().lower()
    return lowered.startswith("https://") or lowered.startswith("http://")


def _safe_voice_prefix(value: str) -> str:
    cleaned = "".join(ch for ch in (value or "aivoice").strip().lower() if ("a" <= ch <= "z") or ("0" <= ch <= "9"))
    cleaned = cleaned or "aivoice"
    if not ("a" <= cleaned[0] <= "z"):
        cleaned = f"a{cleaned}"
    return cleaned[:10]


def _should_try_dashscope_sdk(data: dict[str, Any]) -> bool:
    message = str(data.get("message") or data.get("error_message") or "").lower()
    code = str(data.get("code") or data.get("error_code") or "").lower()
    return "does not support http call" in message or "websocket" in message or code == "invalidparameter"


def _synthesize_with_dashscope_sdk(*, api_key: str, model: str, voice_id: str, text: str) -> bytes:
    try:
        import dashscope
        from dashscope.audio.tts_v2 import SpeechSynthesizer
    except Exception as exc:  # noqa: BLE001 - dependency availability should surface clearly.
        raise AdapterError("DashScope SDK fallback requires python package 'dashscope'. Run: python -m pip install dashscope") from exc

    dashscope.api_key = api_key
    synthesizer = SpeechSynthesizer(model=model, voice=voice_id, language_hints=["zh"])
    audio = synthesizer.call(text)
    if not audio:
        raise AdapterError("DashScope SDK websocket TTS returned empty audio")
    return bytes(audio)


def _extract_voice_id(data: dict[str, Any]) -> str:
    candidates: list[Any] = [data.get("voice_id"), data.get("voice")]
    output = data.get("output")
    if isinstance(output, dict):
        candidates.extend([output.get("voice_id"), output.get("voice")])
    payload = data.get("data")
    if isinstance(payload, dict):
        candidates.extend([payload.get("voice_id"), payload.get("voice")])
    for item in candidates:
        if item:
            return str(item)
    return ""


def _extract_audio_url(data: dict[str, Any]) -> str:
    candidates: list[Any] = [data.get("audio_url"), data.get("url")]
    output = data.get("output")
    if isinstance(output, dict):
        candidates.extend([output.get("audio_url"), output.get("url")])
        audio = output.get("audio")
        if isinstance(audio, dict):
            candidates.extend([audio.get("url"), audio.get("audio_url")])
    payload = data.get("data")
    if isinstance(payload, dict):
        candidates.extend([payload.get("audio_url"), payload.get("url")])
        audio = payload.get("audio")
        if isinstance(audio, dict):
            candidates.extend([audio.get("url"), audio.get("audio_url")])
    for item in candidates:
        if item:
            return str(item)
    return ""


def _extract_audio_bytes(data: dict[str, Any]) -> bytes | None:
    candidates: list[Any] = [data.get("audio_data")]
    output = data.get("output")
    if isinstance(output, dict):
        candidates.extend([output.get("audio_data"), output.get("audio_base64")])
        audio = output.get("audio")
        if isinstance(audio, dict):
            candidates.extend([audio.get("data"), audio.get("base64"), audio.get("audio_data")])
    for item in candidates:
        if isinstance(item, str) and item:
            try:
                return base64.b64decode(item)
            except Exception:
                continue
    return None


def _safe_response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        return response.json()
    except Exception:
        return {"status_code": response.status_code, "text": response.text[:2000]}
