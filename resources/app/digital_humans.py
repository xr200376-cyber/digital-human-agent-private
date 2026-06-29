from datetime import datetime, timezone
from pathlib import Path
import shutil

from app.schemas import (
    CreateDigitalHumanRequest,
    CreateRoleModelRequest,
    CreateVoiceProfileRequest,
    DigitalHumanRoleModel,
    DigitalHumanProfile,
    PatchDigitalHumanRequest,
    RoleModelStatus,
    VoiceProfile,
)
from app.settings import Settings
from app.utils.files import ensure_dir, read_json, write_json


class DigitalHumanStore:
    """Project-scoped file store for synthetic digital human profiles."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.projects_root = ensure_dir(settings.storage_dir / "projects")
        self.index_root = ensure_dir(settings.storage_dir / "digital_humans")

    def project_dir(self, project_id: str) -> Path:
        return ensure_dir(self.projects_root / project_id)

    def digital_human_dir(self, project_id: str, digital_human_id: str) -> Path:
        return ensure_dir(self.project_dir(project_id) / "digital_humans" / digital_human_id)

    def profile_file(self, project_id: str, digital_human_id: str) -> Path:
        return self.digital_human_dir(project_id, digital_human_id) / "profile.json"

    def voice_profile_dir(self, project_id: str, digital_human_id: str) -> Path:
        return ensure_dir(self.digital_human_dir(project_id, digital_human_id) / "voice_profiles")

    def voice_profile_file(self, project_id: str, digital_human_id: str, voice_profile_id: str) -> Path:
        return self.voice_profile_dir(project_id, digital_human_id) / f"{voice_profile_id}.json"

    def role_model_dir(self, project_id: str, digital_human_id: str) -> Path:
        return ensure_dir(self.digital_human_dir(project_id, digital_human_id) / "role_models")

    def role_model_file(self, project_id: str, digital_human_id: str, role_model_id: str) -> Path:
        return self.role_model_dir(project_id, digital_human_id) / f"{role_model_id}.json"

    def index_file(self, digital_human_id: str) -> Path:
        return self.index_root / f"{digital_human_id}.json"

    def create(self, project_id: str, request: CreateDigitalHumanRequest) -> DigitalHumanProfile:
        profile = DigitalHumanProfile(
            project_id=project_id,
            name=request.name,
            avatar_source_type=request.avatar_source_type,
            avatar_style=request.avatar_style,
            selected_avatar_asset=request.selected_avatar_asset,
            metadata=request.metadata,
        )
        self.save(profile)
        return profile

    def save(self, profile: DigitalHumanProfile) -> DigitalHumanProfile:
        profile.updated_at = datetime.now(timezone.utc)
        payload = profile.model_dump(mode="json")
        write_json(self.profile_file(profile.project_id, profile.digital_human_id), payload)
        write_json(self.index_file(profile.digital_human_id), payload)
        return profile

    def get(self, digital_human_id: str) -> DigitalHumanProfile:
        index = self.index_file(digital_human_id)
        if not index.exists():
            raise KeyError(f"digital human not found: {digital_human_id}")
        return DigitalHumanProfile.model_validate(read_json(index))

    def list_for_project(self, project_id: str) -> list[DigitalHumanProfile]:
        root = self.project_dir(project_id) / "digital_humans"
        if not root.exists():
            return []
        profiles = []
        for path in sorted(root.glob("*/profile.json")):
            profiles.append(DigitalHumanProfile.model_validate(read_json(path)))
        return profiles

    def patch(self, digital_human_id: str, request: PatchDigitalHumanRequest) -> DigitalHumanProfile:
        profile = self.get(digital_human_id)
        data = request.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(profile, key, value)
        return self.save(profile)

    def create_voice_profile(
        self, digital_human_id: str, request: CreateVoiceProfileRequest
    ) -> VoiceProfile:
        profile = self.get(digital_human_id)
        voice = VoiceProfile(
            digital_human_id=digital_human_id,
            project_id=profile.project_id,
            name=request.name,
            voice_source_type=request.voice_source_type,
            engine=request.engine,
            sample_asset_id=request.sample_asset_id,
            metadata=request.metadata,
        )
        self.save_voice_profile(voice)
        profile.voice_profile_id = voice.voice_profile_id
        self.save(profile)
        return voice

    def save_voice_profile(self, voice: VoiceProfile) -> VoiceProfile:
        voice.updated_at = datetime.now(timezone.utc)
        write_json(
            self.voice_profile_file(voice.project_id, voice.digital_human_id, voice.voice_profile_id),
            voice.model_dump(mode="json"),
        )
        return voice

    def get_voice_profile(self, digital_human_id: str, voice_profile_id: str) -> VoiceProfile:
        profile = self.get(digital_human_id)
        path = self.voice_profile_file(profile.project_id, digital_human_id, voice_profile_id)
        if not path.exists():
            raise KeyError(f"voice profile not found: {voice_profile_id}")
        return VoiceProfile.model_validate(read_json(path))

    def list_voice_profiles(self, digital_human_id: str) -> list[VoiceProfile]:
        profile = self.get(digital_human_id)
        root = self.voice_profile_dir(profile.project_id, digital_human_id)
        return [VoiceProfile.model_validate(read_json(path)) for path in sorted(root.glob("*.json"))]

    def list_voice_profiles_for_project(
        self,
        project_id: str,
        *,
        visible_asset_owners_only: bool = False,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for profile in self.list_for_project(project_id):
            if visible_asset_owners_only and not self._voice_owner_visible_in_asset_history(profile):
                continue
            for voice in self.list_voice_profiles(profile.digital_human_id):
                payload = voice.model_dump(mode="json")
                payload["owner_digital_human_id"] = profile.digital_human_id
                payload["owner_digital_human_name"] = profile.name
                rows.append(payload)
        return rows

    def _voice_owner_visible_in_asset_history(self, profile: DigitalHumanProfile) -> bool:
        metadata = profile.metadata if isinstance(profile.metadata, dict) else {}
        if metadata.get("system_role") == "preset_voice_library":
            return True
        if profile.digital_human_id.startswith("dh_preset_voice_library_"):
            return True
        return self._profile_has_visible_avatar_asset(profile)

    @staticmethod
    def _profile_has_visible_avatar_asset(profile: DigitalHumanProfile) -> bool:
        metadata = profile.metadata if isinstance(profile.metadata, dict) else {}
        source_tracking = metadata.get("source_tracking") if isinstance(metadata.get("source_tracking"), dict) else {}
        source_video = metadata.get("source_video") if isinstance(metadata.get("source_video"), dict) else {}
        return bool(
            profile.selected_avatar_asset
            or metadata.get("selected_avatar_asset")
            or source_tracking.get("stored_path")
            or source_video.get("source_video_path")
        )

    def delete_voice_profile(self, digital_human_id: str, voice_profile_id: str) -> VoiceProfile:
        profile = self.get(digital_human_id)
        path = self.voice_profile_file(profile.project_id, digital_human_id, voice_profile_id)
        if not path.exists():
            raise KeyError(f"voice profile not found: {voice_profile_id}")
        voice = VoiceProfile.model_validate(read_json(path))
        path.unlink()
        voice_dir = self.voice_profile_dir(profile.project_id, digital_human_id) / voice_profile_id
        self._remove_storage_tree(voice_dir)
        if profile.voice_profile_id == voice_profile_id:
            profile.voice_profile_id = None
            self.save(profile)
        return voice

    def get_voice_profile_for_project(self, project_id: str, voice_profile_id: str) -> VoiceProfile:
        for profile in self.list_for_project(project_id):
            path = self.voice_profile_file(profile.project_id, profile.digital_human_id, voice_profile_id)
            if path.exists():
                return VoiceProfile.model_validate(read_json(path))
        raise KeyError(f"voice profile not found: {voice_profile_id}")

    def delete_digital_human(self, digital_human_id: str) -> DigitalHumanProfile:
        profile = self.get(digital_human_id)
        profile_dir = self.profile_file(profile.project_id, digital_human_id).parent
        asset_dir = self.project_dir(profile.project_id) / "assets" / "digital_humans" / digital_human_id
        index = self.index_file(digital_human_id)
        if index.exists():
            index.unlink()
        self._remove_storage_tree(profile_dir)
        self._remove_storage_tree(asset_dir)
        return profile

    def _remove_storage_tree(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            path.resolve().relative_to(self.settings.storage_dir.resolve())
        except ValueError:
            return
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()

    def create_role_model(self, digital_human_id: str, request: CreateRoleModelRequest) -> DigitalHumanRoleModel:
        profile = self.get(digital_human_id)
        role_model = DigitalHumanRoleModel(
            digital_human_id=digital_human_id,
            project_id=profile.project_id,
            source_video_asset_id=request.source_video_asset_id,
            idle_video_asset_id=request.idle_video_asset_id,
            action_video_asset_id=request.action_video_asset_id,
            pkl_model_path=request.pkl_model_path,
            engine_type=request.engine_type,
            metadata=request.metadata,
        )
        return self.save_role_model(role_model)

    def save_role_model(self, role_model: DigitalHumanRoleModel) -> DigitalHumanRoleModel:
        role_model.updated_at = datetime.now(timezone.utc)
        write_json(
            self.role_model_file(role_model.project_id, role_model.digital_human_id, role_model.role_model_id),
            role_model.model_dump(mode="json"),
        )
        return role_model

    def get_role_model(self, digital_human_id: str, role_model_id: str) -> DigitalHumanRoleModel:
        profile = self.get(digital_human_id)
        path = self.role_model_file(profile.project_id, digital_human_id, role_model_id)
        if not path.exists():
            raise KeyError(f"role model not found: {role_model_id}")
        return DigitalHumanRoleModel.model_validate(read_json(path))

    def list_role_models(self, digital_human_id: str) -> list[DigitalHumanRoleModel]:
        profile = self.get(digital_human_id)
        root = self.role_model_dir(profile.project_id, digital_human_id)
        return [DigitalHumanRoleModel.model_validate(read_json(path)) for path in sorted(root.glob("*.json"))]

    def validate_role_model(self, digital_human_id: str, role_model_id: str) -> DigitalHumanRoleModel:
        role_model = self.get_role_model(digital_human_id, role_model_id)
        checks: dict[str, dict[str, object]] = {}
        blocking_items: list[str] = []

        def check_path(field: str, value: str | None, *, required: bool = False) -> None:
            if not value:
                if required:
                    blocking_items.append(f"{field} is required")
                checks[field] = {"path": value, "exists": False}
                return
            path = Path(value)
            exists = path.exists()
            checks[field] = {"path": value, "exists": exists}
            if not exists:
                blocking_items.append(f"{field} missing: {value}")

        check_path("pkl_model_path", role_model.pkl_model_path, required=True)
        video_values = [
            role_model.source_video_asset_id,
            role_model.idle_video_asset_id,
            role_model.action_video_asset_id,
        ]
        if not any(video_values):
            blocking_items.append("at least one role source/idle/action video asset is required")
        check_path("source_video_asset_id", role_model.source_video_asset_id)
        check_path("idle_video_asset_id", role_model.idle_video_asset_id)
        check_path("action_video_asset_id", role_model.action_video_asset_id)

        role_model.status = RoleModelStatus.ready if not blocking_items else RoleModelStatus.failed
        role_model.validation_report = {
            "checks": checks,
            "blocking_items": blocking_items,
            "policy": "presence-only validation; pkl binary is not parsed in Sprint 13F",
        }
        return self.save_role_model(role_model)

    def readiness(self, digital_human_id: str) -> dict[str, object]:
        profile = self.get(digital_human_id)
        voices = self.list_voice_profiles(digital_human_id)
        blocking_items: list[str] = []
        warnings: list[str] = []
        if not profile.selected_avatar_asset and profile.avatar_source_type != "generated":
            blocking_items.append("avatar selected")
        if not profile.voice_profile_id and not voices:
            blocking_items.append("voice profile selected")
        role_models = self.list_role_models(digital_human_id)
        return {
            "digital_human_id": digital_human_id,
            "ready": not blocking_items,
            "avatar_selected": bool(profile.selected_avatar_asset) or profile.avatar_source_type == "generated",
            "voice_profile_selected": bool(profile.voice_profile_id or voices),
            "voice_engine_ready": True,
            "avatar_render_engine_ready": True,
            "lip_sync_engine_ready": True,
            "role_model_ready": any(role_model.status == RoleModelStatus.ready for role_model in role_models),
            "role_models": [role_model.model_dump(mode="json") for role_model in role_models],
            "final_assembly_ready": True,
            "jianying_ready": True,
            "model_assets_status": "dry-run placeholders",
            "warnings": warnings,
            "blocking_items": blocking_items,
        }
