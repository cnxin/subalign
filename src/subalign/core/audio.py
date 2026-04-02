"""Audio extraction and preprocessing via ffmpeg."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from subalign.models.config import AlignConfig


def _run_ffmpeg(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ffmpeg", *args],
        capture_output=True,
        text=True,
        check=check,
    )


def _run_ffprobe(args: list[str]) -> str:
    result = subprocess.run(
        ["ffprobe", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def get_audio_tracks(video_path: Path) -> list[dict]:
    """List all audio tracks in a video file.

    Returns list of dicts with keys: index, codec, language, channels, title.
    """
    raw = _run_ffprobe([
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "a",
        str(video_path),
    ])
    data = json.loads(raw)
    tracks = []
    for stream in data.get("streams", []):
        tags = stream.get("tags", {})
        tracks.append({
            "index": stream["index"],
            "codec": stream.get("codec_name", "unknown"),
            "language": tags.get("language", "und"),
            "channels": stream.get("channels", 0),
            "title": tags.get("title", ""),
        })
    return tracks


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds."""
    raw = _run_ffprobe([
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(video_path),
    ])
    data = json.loads(raw)
    return float(data["format"]["duration"])


def _cache_key(video_path: Path, track_index: int | None, sample_rate: int) -> str:
    stat = video_path.stat()
    key_str = f"{video_path}:{stat.st_size}:{stat.st_mtime}:{track_index}:{sample_rate}"
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


def extract_audio(
    video_path: Path,
    config: AlignConfig,
    output_path: Path | None = None,
) -> Path:
    """Extract audio from video as 16kHz mono WAV.

    Uses cache to avoid re-extraction for the same video.
    """
    video_path = Path(video_path).resolve()
    cache_dir = config.cache_dir / "audio"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_name = _cache_key(video_path, config.audio_track, config.sample_rate)
    cached = cache_dir / f"{cache_name}.wav"

    if output_path is None:
        output_path = cached

    if output_path.exists():
        return output_path

    args = ["-y", "-i", str(video_path)]

    if config.audio_track is not None:
        args.extend(["-map", f"0:{config.audio_track}"])
    else:
        args.extend(["-map", "0:a:0"])

    args.extend([
        "-ac", "1",
        "-ar", str(config.sample_rate),
        "-vn",
        "-f", "wav",
        str(output_path),
    ])

    _run_ffmpeg(args)
    return output_path


def detect_silences(
    video_path: Path,
    min_duration: float = 3.0,
    noise_threshold: float = -50.0,
) -> list[dict]:
    """Detect silence segments in audio.

    Returns list of dicts with keys: start, end, duration.
    """
    result = subprocess.run(
        [
            "ffmpeg", "-i", str(video_path),
            "-af", f"silencedetect=noise={noise_threshold}dB:d={min_duration}",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    stderr = result.stderr
    silences = []
    current: dict = {}

    for line in stderr.splitlines():
        if "silence_start:" in line:
            parts = line.split("silence_start:")
            current = {"start": float(parts[1].strip())}
        elif "silence_end:" in line:
            parts = line.split("silence_end:")
            rest = parts[1].strip().split("|")
            current["end"] = float(rest[0].strip())
            dur_part = rest[1].strip() if len(rest) > 1 else ""
            if "silence_duration:" in dur_part:
                current["duration"] = float(dur_part.split(":")[1].strip())
            else:
                current["duration"] = current["end"] - current["start"]
            silences.append(current)
            current = {}

    return silences


def detect_black_frames(
    video_path: Path,
    min_duration: float = 1.0,
    pixel_threshold: float = 0.1,
) -> list[dict]:
    """Detect black frame segments in video.

    Returns list of dicts with keys: start, end, duration.
    """
    result = subprocess.run(
        [
            "ffmpeg", "-i", str(video_path),
            "-vf", f"blackdetect=d={min_duration}:pix_th={pixel_threshold}",
            "-an", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    stderr = result.stderr
    blacks = []

    for line in stderr.splitlines():
        if "black_start:" in line:
            parts = {}
            for token in line.split():
                if ":" in token and token[0].isalpha():
                    k, v = token.split(":", 1)
                    try:
                        parts[k] = float(v)
                    except ValueError:
                        pass
            if "black_start" in parts and "black_end" in parts:
                blacks.append({
                    "start": parts["black_start"],
                    "end": parts["black_end"],
                    "duration": parts.get("black_duration", parts["black_end"] - parts["black_start"]),
                })

    return blacks


def detect_scene_changes(
    video_path: Path,
    threshold: float = 0.3,
) -> list[float]:
    """Detect scene change timestamps.

    Returns list of timestamps in seconds.
    """
    result = subprocess.run(
        [
            "ffmpeg", "-i", str(video_path),
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-an", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    stderr = result.stderr
    timestamps = []

    for line in stderr.splitlines():
        if "pts_time:" in line:
            for token in line.split():
                if token.startswith("pts_time:"):
                    try:
                        timestamps.append(float(token.split(":")[1]))
                    except ValueError:
                        pass

    return timestamps


def get_keyframes(video_path: Path) -> list[float]:
    """Extract keyframe timestamps from video.

    Returns list of timestamps in seconds.
    """
    raw = _run_ffprobe([
        "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries", "frame=pts_time,key_frame",
        "-of", "json",
        str(video_path),
    ])
    data = json.loads(raw)
    return [
        float(frame["pts_time"])
        for frame in data.get("frames", [])
        if frame.get("key_frame") == 1 and "pts_time" in frame
    ]
