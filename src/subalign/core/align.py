"""Fast subtitle re-alignment using audio fingerprinting (S2).

Supports ffsubsync (primary) and alass (fallback) for quick timing correction.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pysubs2

from subalign.core.subtitle import load_subtitles, save_subtitles
from subalign.models.config import AlignConfig


def sync_with_ffsubsync(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    reference_subtitle: Path | None = None,
) -> Path:
    """Re-align subtitles using ffsubsync.

    If reference_subtitle is provided, uses subtitle-to-subtitle sync
    (much faster, <1s). Otherwise uses video audio as reference.
    """
    args = ["ffsubsync"]

    if reference_subtitle:
        args.extend([str(reference_subtitle), "-i", str(subtitle_path)])
    else:
        args.extend([str(video_path), "-i", str(subtitle_path)])

    args.extend(["-o", str(output_path)])

    subprocess.run(args, check=True, capture_output=True, text=True)
    return output_path


def sync_with_alass(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
) -> Path:
    """Re-align subtitles using alass (Rust binary)."""
    subprocess.run(
        ["alass", str(video_path), str(subtitle_path), str(output_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def quick_realign(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    config: AlignConfig,
    reference_subtitle: Path | None = None,
    backend: str = "ffsubsync",
) -> Path:
    """Quick re-alignment for S2 scenario.

    Tries the specified backend first, falls back to the alternative.
    """
    video_path = Path(video_path)
    subtitle_path = Path(subtitle_path)
    output_path = Path(output_path)

    if backend == "ffsubsync":
        try:
            return sync_with_ffsubsync(video_path, subtitle_path, output_path, reference_subtitle)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return sync_with_alass(video_path, subtitle_path, output_path)
    else:
        try:
            return sync_with_alass(video_path, subtitle_path, output_path)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return sync_with_ffsubsync(video_path, subtitle_path, output_path, reference_subtitle)


def refine_with_asr(
    video_path: Path,
    aligned_path: Path,
    output_path: Path,
    config: AlignConfig,
    max_offset_ms: int = 500,
) -> Path:
    """Optionally refine alignment using ASR for segments with large offsets.

    Only adjusts segments where the ASR-detected timing differs from the
    current timing by more than max_offset_ms.
    """
    from subalign.core.audio import extract_audio
    from subalign.core.asr import transcribe_audio

    audio_path = extract_audio(video_path, config)
    asr_result = transcribe_audio(audio_path, config)

    subs = load_subtitles(aligned_path)
    dialogue = [e for e in subs.events if e.type == "Dialogue"]

    asr_segments = asr_result.segments
    asr_idx = 0

    for event in dialogue:
        if asr_idx >= len(asr_segments):
            break

        event_mid = (event.start + event.end) / 2
        best_match = None
        best_dist = float("inf")

        for j in range(max(0, asr_idx - 2), min(len(asr_segments), asr_idx + 5)):
            asr_mid = (asr_segments[j].start + asr_segments[j].end) / 2 * 1000
            dist = abs(event_mid - asr_mid)
            if dist < best_dist:
                best_dist = dist
                best_match = j

        if best_match is not None and best_dist > max_offset_ms:
            seg = asr_segments[best_match]
            event.start = int(seg.start * 1000)
            event.end = int(seg.end * 1000)
            asr_idx = best_match + 1
        elif best_match is not None:
            asr_idx = best_match + 1

    save_subtitles(subs, output_path)
    return output_path
