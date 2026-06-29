"""LangGraph integration placeholder.

Codex task:
- Convert VideoPipeline steps into LangGraph nodes.
- Add interrupt after script generation and before final export.
- Persist graph state by task_id/thread_id.
"""

from typing import TypedDict


class VideoGraphState(TypedDict, total=False):
    task_id: str
    script_json: str
    voice_audio: str
    avatar_video: str
    lip_synced_video: str
    final_video: str
    jianying_draft: str
    error: str


def build_video_graph():
    try:
        from langgraph.graph import StateGraph  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Install optional dependency: pip install -e .[agent]") from exc

    graph = StateGraph(VideoGraphState)
    # Codex: add real nodes and edges here.
    return graph
