"""Helpers around ffmpeg and ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .project_model import VideoMetadata


class FFmpegError(RuntimeError):
    """Raised when ffmpeg or ffprobe operations fail."""


def _ensure_binary(name: str) -> str:
    binary = shutil.which(name)
    if not binary:
        raise FFmpegError(
            f"Executable '{name}' was not found in PATH. Install FFmpeg and ensure '{name}' is available."
        )
    return binary


def _run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        raise FFmpegError(str(exc)) from exc
    if result.returncode != 0:
        stderr = result.stderr.strip() or "Unknown FFmpeg error."
        raise FFmpegError(stderr)
    return result


def _parse_fraction(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    if "/" in value:
        numerator, denominator = value.split("/", maxsplit=1)
        if float(denominator) == 0:
            return 0.0
        return float(numerator) / float(denominator)
    return float(value)


def probe_video(video_path: str | Path) -> VideoMetadata:
    """Probe a video file and return normalized metadata."""

    ffprobe = _ensure_binary("ffprobe")
    video_path = str(Path(video_path).resolve())
    result = _run_command(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            video_path,
        ]
    )
    payload = json.loads(result.stdout)
    video_stream = next(
        (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"),
        None,
    )
    if not video_stream:
        raise FFmpegError("No video stream was found in the selected file.")

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    fps = _parse_fraction(video_stream.get("avg_frame_rate")) or _parse_fraction(
        video_stream.get("r_frame_rate")
    )
    duration = float(video_stream.get("duration") or payload.get("format", {}).get("duration") or 0.0)
    raw_nb_frames = video_stream.get("nb_frames")
    if raw_nb_frames and str(raw_nb_frames).isdigit():
        total_frames = int(raw_nb_frames)
    else:
        total_frames = max(1, round(duration * fps)) if fps > 0 and duration > 0 else 1

    return VideoMetadata(
        video_path=video_path,
        width=width,
        height=height,
        fps=fps,
        duration=duration,
        total_frames=total_frames,
    )


def extract_frame(
    video_path: str | Path,
    frame_index: int,
    fps: float,
    output_path: str | Path,
) -> Path:
    """Extract a frame using timestamp seek for responsive navigation."""

    ffmpeg = _ensure_binary("ffmpeg")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    timestamp = frame_index / fps if fps > 0 else 0.0
    result_args = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{timestamp:.6f}",
        "-i",
        str(Path(video_path).resolve()),
        "-frames:v",
        "1",
        str(output),
    ]
    _run_command(result_args)
    if not output.exists():
        raise FFmpegError("FFmpeg finished without producing the requested frame image.")
    return output


def encode_image_sequence_to_video(
    input_pattern: str | Path,
    output_path: str | Path,
    fps: float,
) -> Path:
    """Encode a numbered PNG sequence into a video file."""

    ffmpeg = _ensure_binary("ffmpeg")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _run_command(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            f"{fps:.3f}",
            "-i",
            str(input_pattern),
            "-pix_fmt",
            "yuv420p",
            str(output),
        ]
    )
    if not output.exists():
        raise FFmpegError("FFmpeg failed to encode the exported preview video.")
    return output
