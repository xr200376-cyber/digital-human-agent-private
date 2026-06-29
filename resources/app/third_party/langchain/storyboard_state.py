# storyboard_state.py
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SceneState:
    scene_id: str
    session_id: str
    index: int
    text: str
    illustration_prompt: str = ""
    image_path: Optional[str] = None
    image_status: str = "pending"   # pending / processing / succeed / failed
    image_error: Optional[str] = None
    audio_path: Optional[str] = None
    audio_status: str = "pending"   # pending / succeed / failed
    audio_error: Optional[str] = None
    video_url: Optional[str] = None
    video_status: str = "pending"   # pending / processing / succeed / failed
    video_error: Optional[str] = None


@dataclass
class StoryboardSession:
    session_id: str
    reference_image_path: str
    scenes: List[SceneState] = field(default_factory=list)
    merged_video_path: Optional[str] = None
    merged_video_url: Optional[str] = None
    status: str = "init"            # init / processing / done / failed


class InMemoryStoryboardStore:
    def __init__(self) -> None:
        self._store: dict[str, StoryboardSession] = {}
        self._locks: dict[str, threading.Lock] = {}

    def get_lock(self, session_id: str) -> threading.Lock:
        return self._locks.setdefault(session_id, threading.Lock())

    def get(self, session_id: str) -> StoryboardSession:
        if session_id not in self._store:
            raise KeyError(session_id)
        return self._store[session_id]

    def create(self, session: StoryboardSession) -> StoryboardSession:
        if session.session_id in self._store:
            raise KeyError(f"StoryboardSession already exists: {session.session_id}")
        self._store[session.session_id] = session
        return session

    def save(self, session: StoryboardSession) -> StoryboardSession:
        self._store[session.session_id] = session
        return session

    def exists(self, session_id: str) -> bool:
        return session_id in self._store


def make_storyboard_store() -> InMemoryStoryboardStore:
    return InMemoryStoryboardStore()


def create_storyboard(
    store: InMemoryStoryboardStore,
    session_id: str,
    reference_image_path: str,
    texts: List[str],
) -> StoryboardSession:
    scenes = [
        SceneState(
            scene_id=str(uuid.uuid4()),
            session_id=session_id,
            index=i,
            text=text,
        )
        for i, text in enumerate(texts)
    ]
    sb = StoryboardSession(
        session_id=session_id,
        reference_image_path=reference_image_path,
        scenes=scenes,
    )
    return store.create(sb)
