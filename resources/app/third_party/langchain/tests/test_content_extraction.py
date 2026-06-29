import sys
import types

import content_extraction


def test_resolve_ffmpeg_uses_imageio_binary_when_system_ffmpeg_missing(monkeypatch):
    fake_imageio = types.SimpleNamespace(get_ffmpeg_exe=lambda: "C:/tools/imageio/ffmpeg.exe")
    monkeypatch.setattr(content_extraction.shutil, "which", lambda name: None)
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", fake_imageio)

    assert content_extraction._resolve_ffmpeg_executable() == "C:/tools/imageio/ffmpeg.exe"


def test_extract_from_video_passes_loaded_audio_to_whisper(monkeypatch, tmp_path):
    fake_audio = object()

    class FakeModel:
        def transcribe(self, audio, language):
            assert audio is fake_audio
            assert language == "zh"
            return {"text": "sample text"}

    fake_whisper = types.SimpleNamespace(load_model=lambda name: FakeModel())
    fake_opencc = types.SimpleNamespace(
        OpenCC=lambda mode: types.SimpleNamespace(convert=lambda text: f"converted {text}")
    )

    monkeypatch.setitem(sys.modules, "whisper", fake_whisper)
    monkeypatch.setitem(sys.modules, "opencc", fake_opencc)
    monkeypatch.setattr(content_extraction, "_resolve_ffmpeg_executable", lambda: "ffmpeg.exe")
    monkeypatch.setattr(content_extraction, "_load_wav_for_whisper", lambda path: fake_audio)

    def fake_run(args, capture_output, text):
        assert args[0] == "ffmpeg.exe"
        assert "-ar" in args
        return types.SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(content_extraction.subprocess, "run", fake_run)

    assert content_extraction.extract_from_video(tmp_path / "input.mp4") == "converted sample text"
