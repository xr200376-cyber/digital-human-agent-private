"""可灵 service 单元测试（全部 mock，不发真实 HTTP）"""
import os
import time
from unittest.mock import MagicMock, patch

import pytest


# ── JWT 鉴权 ────────────────────────────────────────────────────────────────

def test_make_jwt_contains_iss():
    from kling_service import _make_jwt
    token = _make_jwt("ak_test", "sk_test")
    import jwt as pyjwt
    payload = pyjwt.decode(token, "sk_test", algorithms=["HS256"])
    header = pyjwt.get_unverified_header(token)
    assert payload["iss"] == "ak_test"
    assert payload["exp"] > int(time.time())
    assert header["alg"] == "HS256"
    assert header["typ"] == "JWT"


def test_base_url_defaults_to_global():
    from kling_service import _base_url
    with patch.dict(os.environ, {}, clear=True):
        assert _base_url() == "https://api.klingai.com"


def test_get_credentials_raises_when_missing():
    from kling_service import _get_credentials
    with patch.dict(os.environ, {}, clear=True):
        # Ensure both keys are absent
        os.environ.pop("KLING_ACCESS_KEY_ID", None)
        os.environ.pop("KLING_ACCESS_KEY_SECRET", None)
        with pytest.raises(EnvironmentError, match="KLING_ACCESS_KEY_ID"):
            _get_credentials()


# ── 轮询 ────────────────────────────────────────────────────────────────────

def test_poll_avatar_task_returns_url_on_succeed():
    from kling_service import _poll_avatar_task
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {
            "task_status": "succeed",
            "task_result": {"videos": [{"url": "https://example.com/v.mp4"}]},
        }
    }
    with patch("kling_service.requests.request", return_value=mock_resp) as mock_request, \
         patch.dict(os.environ, {"KLING_ACCESS_KEY_ID": "ak", "KLING_ACCESS_KEY_SECRET": "sk"}):
        url = _poll_avatar_task("task_abc", timeout=10)
    assert url == "https://example.com/v.mp4"
    assert "/v1/videos/avatar/image2video/task_abc" in mock_request.call_args.args[1]


def test_poll_avatar_task_raises_on_failed():
    from kling_service import _poll_avatar_task
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"task_status": "failed"}}
    with patch("kling_service.requests.request", return_value=mock_resp), \
         patch.dict(os.environ, {"KLING_ACCESS_KEY_ID": "ak", "KLING_ACCESS_KEY_SECRET": "sk"}):
        with pytest.raises(RuntimeError, match="任务.*失败"):
            _poll_avatar_task("task_xyz", timeout=10)


def test_request_json_falls_back_from_singapore_to_global():
    from kling_service import _request_json

    first = MagicMock()
    first.ok = False
    first.status_code = 401
    first.headers = {}
    first.json.return_value = {"code": 1002, "message": "access key not found"}
    first.text = '{"code":1002,"message":"access key not found"}'

    second = MagicMock()
    second.ok = True

    with patch(
        "kling_service.requests.request",
        side_effect=[first, second],
    ) as mock_request, patch.dict(
        os.environ,
        {
            "KLING_ACCESS_KEY_ID": "ak",
            "KLING_ACCESS_KEY_SECRET": "sk",
            "KLING_API_BASE_URL": "https://api-singapore.klingai.com",
        },
        clear=True,
    ):
        resp = _request_json("POST", "/v1/videos/avatar/image2video", json_body={"image": "x"})

    assert resp is second
    assert mock_request.call_args_list[0].args[1].startswith("https://api-singapore.klingai.com/")
    assert mock_request.call_args_list[1].args[1].startswith("https://api.klingai.com/")


def test_request_json_raises_kling_api_error_with_detail():
    from kling_service import KlingAPIError, _request_json

    resp = MagicMock()
    resp.ok = False
    resp.status_code = 401
    resp.headers = {}
    resp.json.return_value = {
        "code": 1002,
        "message": "Auth failed",
        "request_id": "req_1",
    }

    with patch("kling_service.requests.request", return_value=resp), patch.dict(
        os.environ,
        {"KLING_ACCESS_KEY_ID": "ak", "KLING_ACCESS_KEY_SECRET": "sk"},
        clear=True,
    ):
        with pytest.raises(KlingAPIError) as exc_info:
            _request_json("POST", "/v1/videos/avatar/image2video", json_body={"image": "x"})

    assert exc_info.value.status_code == 401
    assert "code=1002" in str(exc_info.value)
    assert "request_id=req_1" in str(exc_info.value)


# ── 数字人口播 ───────────────────────────────────────────────────────────────

def test_generate_avatar_video_calls_lip_sync(tmp_path):
    from kling_service import generate_avatar_video

    image = tmp_path / "avatar.png"
    audio = tmp_path / "test.mp3"
    image.write_bytes(b"fake_image")
    audio.write_bytes(b"fake_audio")

    task_resp = MagicMock()
    task_resp.ok = True
    task_resp.json.return_value = {"data": {"task_id": "avatar_task_1"}}

    poll_resp = MagicMock()
    poll_resp.ok = True
    poll_resp.json.return_value = {
        "data": {
            "task_status": "succeed",
            "task_result": {"videos": [{"url": "https://cdn.kling.ai/avatar.mp4"}]},
        }
    }

    with patch("kling_service.requests.request", side_effect=[task_resp, poll_resp]) as mock_request, \
         patch.dict(os.environ, {"KLING_ACCESS_KEY_ID": "ak", "KLING_ACCESS_KEY_SECRET": "sk"}):
        url = generate_avatar_video(image, audio)

    assert url == "https://cdn.kling.ai/avatar.mp4"
    assert "avatar/image2video" in mock_request.call_args_list[0].args[1]
    body = mock_request.call_args_list[0].kwargs["json"]
    assert body["image"]
    assert body["sound_file"]
