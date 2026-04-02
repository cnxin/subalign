"""BD multi-episode splitting and subtitle concatenation (S6).

Detects episode boundaries in BD video files using multiple signals:
- Silence detection (long gaps between episodes)
- Black frame detection
- Duration constraints (typical anime ~23-25min)
- Optional OP audio fingerprinting
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pysubs2

from subalign.core.audio import detect_black_frames, detect_silences, get_video_duration
from subalign.core.subtitle import load_subtitles, save_subtitles
from subalign.models.config import AlignConfig


@dataclass
class EpisodeBoundary:
    """Detected episode boundary."""
    start: float   # seconds
    end: float     # seconds
    confidence: float
    signals: list[str]  # which signals confirmed this boundary


@dataclass
class SplitResult:
    """Result of BD splitting operation."""
    boundaries: list[EpisodeBoundary]
    total_duration: float
    episode_count: int


def _cross_validate_boundaries(
    silences: list[dict],
    blacks: list[dict],
    tolerance: float = 2.0,
) -> list[dict]:
    """Find points where both silence and black frames coincide."""
    candidates = []

    for silence in silences:
        s_mid = (silence["start"] + silence["end"]) / 2

        for black in blacks:
            b_mid = (black["start"] + black["end"]) / 2

            if abs(s_mid - b_mid) < tolerance:
                candidates.append({
                    "time": (s_mid + b_mid) / 2,
                    "silence": silence,
                    "black": black,
                    "signals": ["silence", "black"],
                    "confidence": 0.9,
                })
                break
        else:
            # Silence without black frame - lower confidence
            candidates.append({
                "time": s_mid,
                "silence": silence,
                "signals": ["silence"],
                "confidence": 0.5,
            })

    # Also add black frames without matching silence
    for black in blacks:
        b_mid = (black["start"] + black["end"]) / 2
        already_matched = any(abs(c["time"] - b_mid) < tolerance for c in candidates)
        if not already_matched and black["duration"] >= 2.0:
            candidates.append({
                "time": b_mid,
                "silence": None,
                "black": black,
                "signals": ["black"],
                "confidence": 0.4,
            })

    candidates.sort(key=lambda c: c["time"])
    return candidates


def _filter_by_duration(
    candidates: list[dict],
    total_duration: float,
    min_ep: int = 1200,
    max_ep: int = 1800,
) -> list[dict]:
    """Filter boundary candidates by episode duration constraints."""
    if not candidates:
        return []

    filtered = []
    prev_time = 0.0

    for candidate in candidates:
        gap = candidate["time"] - prev_time

        if min_ep <= gap <= max_ep:
            filtered.append(candidate)
            prev_time = candidate["time"]
        elif gap > max_ep:
            # Too long - might have missed a boundary, keep it anyway
            filtered.append(candidate)
            prev_time = candidate["time"]
        # If gap < min_ep, skip this candidate (too close to previous)

    # Verify last segment
    if filtered:
        last_gap = total_duration - filtered[-1]["time"]
        if last_gap < min_ep * 0.5:
            # Last segment too short - probably not a real boundary
            filtered.pop()

    return filtered


def detect_episode_boundaries(
    video_path: Path,
    config: AlignConfig,
) -> SplitResult:
    """Detect episode boundaries in a BD multi-episode video."""
    video_path = Path(video_path)
    total_duration = get_video_duration(video_path)

    silences = detect_silences(
        video_path,
        min_duration=config.silence_min_duration,
        noise_threshold=config.silence_threshold,
    )

    blacks = detect_black_frames(
        video_path,
        min_duration=config.black_min_duration,
    )

    candidates = _cross_validate_boundaries(silences, blacks)
    min_ep, max_ep = config.ep_duration_range
    filtered = _filter_by_duration(candidates, total_duration, min_ep, max_ep)

    # Build episode boundaries
    boundaries = []
    prev_end = 0.0

    for i, candidate in enumerate(filtered):
        boundary_time = candidate["time"]

        boundaries.append(EpisodeBoundary(
            start=prev_end,
            end=boundary_time,
            confidence=candidate["confidence"],
            signals=candidate["signals"],
        ))

        # Next episode starts after the gap
        silence = candidate.get("silence")
        if silence:
            prev_end = silence["end"]
        else:
            black = candidate.get("black")
            prev_end = black["end"] if black else boundary_time

    # Last episode
    if prev_end < total_duration - 60:  # at least 1 min remaining
        boundaries.append(EpisodeBoundary(
            start=prev_end,
            end=total_duration,
            confidence=0.8,
            signals=["duration"],
        ))

    return SplitResult(
        boundaries=boundaries,
        total_duration=total_duration,
        episode_count=len(boundaries),
    )


def concatenate_subtitles(
    boundaries: list[EpisodeBoundary],
    subtitle_paths: list[Path],
    output_path: Path,
    verify_with_asr: bool = False,
    video_path: Path | None = None,
    config: AlignConfig | None = None,
) -> Path:
    """Concatenate multiple single-episode subtitle files into one.

    Each subtitle file's timestamps are offset by the episode start time.
    """
    if len(subtitle_paths) != len(boundaries):
        raise ValueError(
            f"Subtitle file count ({len(subtitle_paths)}) doesn't match "
            f"detected episode count ({len(boundaries)}). "
            f"Use --detect-only to check boundaries first."
        )

    merged = pysubs2.SSAFile()
    styles_added = set()

    for i, (boundary, sub_path) in enumerate(zip(boundaries, subtitle_paths)):
        subs = load_subtitles(sub_path)
        offset_ms = int(boundary.start * 1000)

        # Copy styles (only once per unique style name)
        for name, style in subs.styles.items():
            if name not in styles_added:
                merged.styles[name] = style
                styles_added.add(name)

        for event in subs.events:
            new_event = event.copy()
            new_event.start += offset_ms
            new_event.end += offset_ms
            merged.events.append(new_event)

    merged.events.sort(key=lambda e: e.start)
    save_subtitles(merged, output_path)

    return output_path


def format_boundaries_report(result: SplitResult) -> str:
    """Format episode boundaries as a human-readable report."""
    lines = [
        f"Total duration: {result.total_duration:.1f}s "
        f"({result.total_duration / 60:.1f}min)",
        f"Detected episodes: {result.episode_count}",
        "",
    ]

    for i, ep in enumerate(result.boundaries, 1):
        duration = ep.end - ep.start
        signals = ", ".join(ep.signals)
        lines.append(
            f"  EP{i:02d}: {ep.start:.1f}s - {ep.end:.1f}s "
            f"({duration / 60:.1f}min) "
            f"[{signals}] confidence={ep.confidence:.1%}"
        )

    return "\n".join(lines)
