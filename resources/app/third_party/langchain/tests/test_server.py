from fastapi.testclient import TestClient

from server import app
from workflow_state import WorkflowState, WorkflowStep


def test_workflow_status_returns_avatar_image_url():
    class StubStore:
        def __call__(self, session_id: str):
            assert session_id == "session-1"
            return WorkflowState(
                session_id="session-1",
                current_step=WorkflowStep.AUDIO_DONE,
                source="manual text",
                source_type="text",
                extracted_text="原文",
                final_text="确认文本",
                audio_path="/tmp/session-1.mp3",
                avatar_image_path="/tmp/session-1_avatar.png",
                video_mode="avatar",
            )

    app.state.workflow_store = StubStore()
    client = TestClient(app)

    response = client.get("/workflow/session-1/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["avatar_image_ready"] is True
    assert payload["avatar_image_url"] == "/uploads/session-1_avatar.png"
    assert payload["video_status"] == ""
    assert payload["video_error"] is None


def test_root_serves_built_frontend():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "数字人内容生成" in response.text


def test_workflow_rewrite_reports_missing_moonshot_key():
    class StubStore:
        def __call__(self, session_id: str):
            assert session_id == "session-1"
            return WorkflowState(
                session_id="session-1",
                current_step=WorkflowStep.EXTRACTED,
                source="manual text",
                source_type="text",
                extracted_text="原文",
            )

    app.state.workflow_store = StubStore()
    app.state.router_llm = None
    client = TestClient(app)

    response = client.post("/workflow/session-1/rewrite", json={"style_id": "news"})

    assert response.status_code == 503
    assert "MOONSHOT_API_KEY" in response.json()["detail"]
