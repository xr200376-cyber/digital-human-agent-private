# video_merge_service.py
"""
用 ffmpeg 把多段视频拼接为一个完整视频。

使用 ffmpeg concat demuxer（-f concat -safe 0），需要系统安装 ffmpeg。
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

import requests


def download_video(url: str, dest: Path) -> Path:
    """Download a remote video URL to a local file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=300, stream=True)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    return dest


def merge_videos(video_paths: List[Path], output_path: Path) -> Path:
    """
    Concatenate local video files using ffmpeg concat demuxer.

    Args:
        video_paths: Ordered list of local video file paths.
        output_path: Destination for the merged video.

    Returns:
        output_path on success.

    Raises:
        RuntimeError: if ffmpeg exits with non-zero status.
        FileNotFoundError: if ffmpeg is not installed.
    """
    if not video_paths:
        raise ValueError("video_paths 不能为空")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    fd, concat_file = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w") as f:
            for p in video_paths:
                f.write(f"file '{p.resolve()}'\n")

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg 失败（exit {result.returncode}）：{result.stderr[-800:]}"
            )
    finally:
        try:
            os.unlink(concat_file)
        except OSError:
            pass

    return output_path


def download_and_merge(
    video_urls: List[str],
    session_id: str,
    generated_dir: Path,
) -> Path:
    """
    Download each URL, then merge all into one file.

    Local files: generated_dir/{session_id}_scene_{index}.mp4
    Output:      generated_dir/{session_id}_merged.mp4
    """
    local_paths: List[Path] = []
    for i, url in enumerate(video_urls):
        dest = generated_dir / f"{session_id}_scene_{i}.mp4"
        if not dest.exists():
            download_video(url, dest)
        local_paths.append(dest)

    output = generated_dir / f"{session_id}_merged.mp4"
    return merge_videos(local_paths, output)
