"""OP/ED frame-level subtitle alignment (S4).

Snaps subtitle timings to nearest keyframe or audio beat point
for precise visual synchronization.
"""

from __future__ import annotations

from pathlib import Path

import pysubs2

from subalign.core.audio import detect_scene_changes, get_keyframes
from subalign.core.subtitle import load_subtitles, save_subtitles


def _detect_beats(audio_path: Path) -> list[float]:
    """Detect audio beat/onset timestamps using librosa."""
    try:
        import librosa
        import numpy as np
    except ImportError:
        return []

    y, sr = librosa.load(str(audio_path), sr=22050)
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="time")
    return onset_frames.tolist()


def _find_nearest(timestamps: list[float], target: float, tolerance: float = 0.1) -> float | None:
    """Find nearest timestamp within tolerance (seconds)."""
    if not timestamps:
        return None
    best = min(timestamps, key=lambda t: abs(t - target))
    if abs(best - target) <= tolerance:
        return best
    return None


def snap_to_keyframes(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    audio_path: Path | None = None,
    use_scene_changes: bool = True,
    use_beats: bool = True,
    frame_tolerance: float = 0.08,
    min_display_ms: int = 500,
) -> Path:
    """Snap subtitle timings to nearest keyframes, scene changes, or beats.

    Priority: scene change > keyframe > beat point.
    """
    snap_points: list[float] = []

    # Scene changes (highest priority)
    if use_scene_changes:
        scenes = detect_scene_changes(video_path)
        snap_points.extend(scenes)

    # Keyframes
    keyframes = get_keyframes(video_path)
    snap_points.extend(keyframes)

    # Audio beats (lowest priority, only for OP/ED music sections)
    beats: list[float] = []
    if use_beats and audio_path:
        beats = _detect_beats(audio_path)

    snap_points = sorted(set(snap_points))

    subs = load_subtitles(subtitle_path)
    dialogue = [e for e in subs.events if e.type == "Dialogue"]

    for event in dialogue:
        start_sec = event.start / 1000.0
        end_sec = event.end / 1000.0

        # Try snapping start time
        snapped_start = _find_nearest(snap_points, start_sec, frame_tolerance)
        if snapped_start is None and beats:
            snapped_start = _find_nearest(beats, start_sec, frame_tolerance)

        # Try snapping end time
        snapped_end = _find_nearest(snap_points, end_sec, frame_tolerance)
        if snapped_end is None and beats:
            snapped_end = _find_nearest(beats, end_sec, frame_tolerance)

        new_start = int((snapped_start or start_sec) * 1000)
        new_end = int((snapped_end or end_sec) * 1000)

        # Enforce minimum display time
        if new_end - new_start < min_display_ms:
            new_end = new_start + min_display_ms

        event.start = new_start
        event.end = new_end

    save_subtitles(subs, output_path)
    return output_path
