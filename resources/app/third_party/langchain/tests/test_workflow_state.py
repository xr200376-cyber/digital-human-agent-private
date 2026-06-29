import os
from unittest.mock import patch

import pytest

from workflow_state import (
    WorkflowStep,
    create_workflow,
    list_workflows,
    make_workflow_store,
    save_workflow,
)


def test_memory_store_persists_state_updates():
    with patch.dict(os.environ, {}, clear=True):
        store = make_workflow_store()
        state = create_workflow(store, "manual text", "text", "原文")

        state.final_text = "确认后的文本"
        state.current_step = WorkflowStep.CONFIRMED
        state.video_mode = "avatar"
        state.video_status = "queued"
        save_workflow(store, state)

        loaded = store(state.session_id)
        assert loaded.final_text == "确认后的文本"
        assert loaded.current_step == WorkflowStep.CONFIRMED
        assert loaded.video_mode == "avatar"
        assert loaded.video_status == "queued"


def test_memory_store_raises_for_missing_session():
    with patch.dict(os.environ, {}, clear=True):
        store = make_workflow_store()
        with pytest.raises(KeyError):
            store("missing-session")


def test_memory_store_lists_recent_sessions_with_video_metadata():
    with patch.dict(os.environ, {}, clear=True):
        store = make_workflow_store()
        state = create_workflow(store, "manual text", "text", "这是一段很长的测试文本，用来验证任务列表预览会被截断并带回视频信息。")
        state.final_text = "确认后的文本"
        state.current_step = WorkflowStep.VIDEO_DONE
        state.video_mode = "avatar"
        state.video_status = "succeed"
        state.video_url = "https://cdn.example.com/video.mp4"
        save_workflow(store, state)

        [summary] = list_workflows(store)

    assert summary.session_id == state.session_id
    assert summary.current_step == "video_done"
    assert summary.video_mode == "avatar"
    assert summary.video_url == "https://cdn.example.com/video.mp4"
    assert summary.text_preview == "确认后的文本"
