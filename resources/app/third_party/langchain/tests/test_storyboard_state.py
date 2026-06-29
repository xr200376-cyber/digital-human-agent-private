import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from storyboard_state import (
    InMemoryStoryboardStore,
    create_storyboard,
)


def test_create_storyboard_creates_scenes():
    store = InMemoryStoryboardStore()
    sb = create_storyboard(store, "sess-1", "/tmp/ref.png", ["句子一。", "句子二。"])
    assert sb.session_id == "sess-1"
    assert len(sb.scenes) == 2
    assert sb.scenes[0].index == 0
    assert sb.scenes[0].text == "句子一。"
    assert sb.scenes[1].index == 1
    assert sb.scenes[0].image_status == "pending"
    assert sb.scenes[0].video_status == "pending"


def test_store_get_raises_on_missing():
    store = InMemoryStoryboardStore()
    try:
        store.get("nope")
        assert False, "should raise"
    except KeyError:
        pass


def test_store_save_and_retrieve():
    store = InMemoryStoryboardStore()
    sb = create_storyboard(store, "sess-2", "/tmp/ref.png", ["一句话。"])
    sb.scenes[0].video_status = "succeed"
    sb.scenes[0].video_url = "https://example.com/video.mp4"
    store.save(sb)

    loaded = store.get("sess-2")
    assert loaded is sb  # in-memory store returns same object reference
    assert loaded.scenes[0].video_status == "succeed"
    assert loaded.scenes[0].video_url == "https://example.com/video.mp4"


def test_store_create_raises_on_duplicate():
    store = InMemoryStoryboardStore()
    create_storyboard(store, "dup", "/tmp/ref.png", ["句子。"])
    try:
        create_storyboard(store, "dup", "/tmp/ref.png", ["另一句。"])
        assert False, "should raise KeyError"
    except KeyError:
        pass


def test_store_exists():
    store = InMemoryStoryboardStore()
    assert not store.exists("x")
    create_storyboard(store, "x", "/tmp/ref.png", ["句子。"])
    assert store.exists("x")
