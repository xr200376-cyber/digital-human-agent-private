from pathlib import Path

from app.adapters.llm import DryRunLLMAdapter, LocalModelAdapter, OpenAICompatibleAdapter
from app.reference_videos import ReferenceVideoStore
from app.schemas import RewriteScriptRequest, ScriptRewrite, ScriptTemplate
from app.settings import Settings
from app.utils.files import ensure_dir, read_json, write_json


class ScriptRewriteStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.reference_store = ReferenceVideoStore(settings)

    def reference_dir(self, project_id: str, reference_id: str) -> Path:
        return self.reference_store.reference_dir(project_id, reference_id)

    def rewrite_root(self, project_id: str, reference_id: str) -> Path:
        return ensure_dir(self.reference_dir(project_id, reference_id) / "rewrites")

    def rewrite_dir(self, project_id: str, reference_id: str, rewrite_id: str) -> Path:
        return ensure_dir(self.rewrite_root(project_id, reference_id) / rewrite_id)

    def rewrite_file(self, project_id: str, reference_id: str, rewrite_id: str) -> Path:
        return self.rewrite_dir(project_id, reference_id, rewrite_id) / "rewrite.json"

    def rewrite(self, reference_id: str, request: RewriteScriptRequest) -> ScriptRewrite:
        reference = self.reference_store.get(reference_id)
        if reference.project_id != request.project_id:
            raise ValueError(f"reference {reference_id} does not belong to project {request.project_id}")
        analysis = self.reference_store.analysis_payload(reference_id)
        template = self._template_from_analysis(request, analysis)
        draft = ScriptRewrite(
            reference_id=reference_id,
            project_id=request.project_id,
            request=request,
            template=template,
            rewritten_scripts_json="",
            script_scores_json="",
            rewrite_report_json="",
        )
        out_dir = self.rewrite_dir(request.project_id, reference_id, draft.rewrite_id)
        result = self._llm_adapter().rewrite_scripts(
            reference_analysis=analysis,
            request=request.model_dump(mode="json"),
            out_dir=out_dir,
        )
        rewritten = read_json(result.rewritten_scripts_path)
        draft.rewritten_scripts_json = str(result.rewritten_scripts_path)
        draft.script_scores_json = str(result.script_scores_path)
        draft.rewrite_report_json = str(result.rewrite_report_path)
        draft.scripts = rewritten.get("scripts", [])
        self.save(draft)
        return draft

    def save(self, rewrite: ScriptRewrite) -> ScriptRewrite:
        write_json(
            self.rewrite_file(rewrite.project_id, rewrite.reference_id, rewrite.rewrite_id),
            rewrite.model_dump(mode="json"),
        )
        return rewrite

    def list_for_reference(self, reference_id: str) -> list[ScriptRewrite]:
        reference = self.reference_store.get(reference_id)
        root = self.rewrite_root(reference.project_id, reference_id)
        return [ScriptRewrite.model_validate(read_json(path)) for path in sorted(root.glob("*/rewrite.json"), reverse=True)]

    def _template_from_analysis(self, request: RewriteScriptRequest, analysis: dict[str, object]) -> ScriptTemplate:
        reference_script = analysis.get("reference_script", {})
        style_summary = analysis.get("style_summary", {})
        if not isinstance(reference_script, dict):
            reference_script = {}
        if not isinstance(style_summary, dict):
            style_summary = {}
        return ScriptTemplate(
            reference_id=request.reference_id,
            project_id=request.project_id,
            platform=request.platform,
            tone=request.tone,
            hook_pattern=str(reference_script.get("hook") or "question hook"),
            body_structure=[str(item) for item in reference_script.get("body_points", [])],
            cta_pattern=str(reference_script.get("cta") or "clear action"),
            source_summary=style_summary,
        )

    def _llm_adapter(self):
        engine = (self.settings.llm_engine or "dryrun").lower()
        if engine == "openai_compatible":
            return OpenAICompatibleAdapter(
                dry_run=self.settings.dry_run,
                enabled=self.settings.openai_compatible_enabled,
                base_url=self.settings.openai_compatible_base_url,
                api_key=self.settings.openai_compatible_api_key,
                model=self.settings.openai_compatible_model,
            )
        if engine == "local_model":
            return LocalModelAdapter(
                dry_run=self.settings.dry_run,
                enabled=self.settings.local_model_enabled,
                model_path=self.settings.local_model_path,
            )
        return DryRunLLMAdapter()
