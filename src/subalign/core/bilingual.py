"""Bilingual subtitle alignment (S5).

Aligns a secondary language subtitle to the primary language timeline.
Supports line-count matching, anchor-based alignment, and semantic DP alignment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pysubs2
from rapidfuzz import fuzz

from subalign.core.asr import transcribe_audio
from subalign.core.audio import extract_audio
from subalign.core.subtitle import (
    add_bilingual_styles,
    get_dialogue_events,
    get_plain_text_lines,
    load_subtitles,
    merge_bilingual_events,
    save_subtitles,
)
from subalign.models.config import AlignConfig


@dataclass
class LineMapping:
    """Mapping between primary and secondary subtitle lines."""
    primary_indices: list[int]
    secondary_indices: list[int]
    confidence: float


def _align_by_line_count(
    primary_events: list[pysubs2.SSAEvent],
    secondary_events: list[pysubs2.SSAEvent],
) -> list[LineMapping] | None:
    """Direct 1:1 alignment when line counts match."""
    if len(primary_events) != len(secondary_events):
        return None

    return [
        LineMapping(
            primary_indices=[i],
            secondary_indices=[i],
            confidence=1.0,
        )
        for i in range(len(primary_events))
    ]


def _align_by_anchors(
    primary_events: list[pysubs2.SSAEvent],
    secondary_events: list[pysubs2.SSAEvent],
    tolerance_ms: int = 2000,
) -> list[LineMapping] | None:
    """Align using overlapping time ranges as anchors.

    Only works when both subtitle files have timing info.
    """
    if not all(e.start > 0 or e.end > 0 for e in primary_events):
        return None
    if not all(e.start > 0 or e.end > 0 for e in secondary_events):
        return None

    mappings = []
    sec_used = set()

    for pi, pri in enumerate(primary_events):
        best_si = None
        best_overlap = 0

        for si, sec in enumerate(secondary_events):
            if si in sec_used:
                continue
            overlap_start = max(pri.start, sec.start)
            overlap_end = min(pri.end, sec.end)
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap or (overlap == 0 and abs(pri.start - sec.start) < tolerance_ms):
                best_overlap = overlap
                best_si = si

        if best_si is not None:
            sec_used.add(best_si)
            mappings.append(LineMapping(
                primary_indices=[pi],
                secondary_indices=[best_si],
                confidence=min(1.0, best_overlap / max(1, pri.end - pri.start)),
            ))
        else:
            mappings.append(LineMapping(
                primary_indices=[pi],
                secondary_indices=[],
                confidence=0.0,
            ))

    return mappings


def _align_by_dp(
    primary_lines: list[str],
    secondary_lines: list[str],
) -> list[LineMapping]:
    """Dynamic programming alignment allowing 1:N and N:1 mappings.

    Uses sequence structure (order preservation) rather than text similarity,
    since the two languages may have very different text.
    """
    n = len(primary_lines)
    m = len(secondary_lines)

    if n == 0 or m == 0:
        return []

    # Simple ratio-based alignment: distribute secondary lines proportionally
    ratio = m / n
    mappings = []

    for pi in range(n):
        sec_start = int(pi * ratio)
        sec_end = int((pi + 1) * ratio)
        sec_end = max(sec_end, sec_start + 1)
        sec_end = min(sec_end, m)

        mappings.append(LineMapping(
            primary_indices=[pi],
            secondary_indices=list(range(sec_start, sec_end)),
            confidence=0.8 if sec_end - sec_start == 1 else 0.6,
        ))

    return mappings


def align_bilingual(
    video_path: Path,
    primary_path: Path,
    secondary_path: Path,
    output_path: Path,
    config: AlignConfig,
) -> Path:
    """Align bilingual subtitles.

    Strategy (by priority):
    1. Line count match → direct 1:1 alignment
    2. Both have timing → anchor-based overlap alignment
    3. Fallback → proportional DP alignment

    The primary language gets ASR-based timing; secondary inherits it.
    """
    primary_subs = load_subtitles(primary_path)
    secondary_subs = load_subtitles(secondary_path)

    pri_events = get_dialogue_events(primary_subs)
    sec_events = get_dialogue_events(secondary_subs)

    # Ensure primary has timing (via ASR if needed)
    has_timing = any(e.start > 0 for e in pri_events)
    if not has_timing:
        from subalign.core.matcher import full_align
        aligned_pri_path = output_path.with_suffix(".pri_aligned.ass")
        full_align(video_path, primary_path, aligned_pri_path, config)
        primary_subs = load_subtitles(aligned_pri_path)
        pri_events = get_dialogue_events(primary_subs)

    # Try alignment strategies in order
    mappings = _align_by_line_count(pri_events, sec_events)

    if mappings is None:
        mappings = _align_by_anchors(pri_events, sec_events)

    if mappings is None:
        pri_lines = get_plain_text_lines(primary_subs)
        sec_lines = get_plain_text_lines(secondary_subs)
        mappings = _align_by_dp(pri_lines, sec_lines)

    # Apply timing from primary to secondary
    timed_secondary: list[pysubs2.SSAEvent] = []

    style = config.bilingual_style
    pri_style = config.primary_lang or "JP"
    sec_style = config.secondary_lang or "CN"

    for mapping in mappings:
        if not mapping.primary_indices or not mapping.secondary_indices:
            # Unmatched lines - mark for review
            for si in mapping.secondary_indices:
                event = sec_events[si].copy()
                event.text = "{\\c&H0000FF&}[REVIEW] " + event.text
                timed_secondary.append(event)
            continue

        # Get time range from primary
        pri_start = min(pri_events[pi].start for pi in mapping.primary_indices)
        pri_end = max(pri_events[pi].end for pi in mapping.primary_indices)

        # Distribute time range across secondary lines
        sec_count = len(mapping.secondary_indices)
        duration = pri_end - pri_start
        per_line = duration // max(sec_count, 1)

        for idx, si in enumerate(mapping.secondary_indices):
            event = sec_events[si].copy()
            event.start = pri_start + idx * per_line
            event.end = pri_start + (idx + 1) * per_line if idx < sec_count - 1 else pri_end
            event.style = sec_style.upper()

            if mapping.confidence < 0.5:
                event.text = "{\\c&H0000FF&}[REVIEW] " + event.text

            timed_secondary.append(event)

    # Set styles on primary events
    for event in pri_events:
        event.style = pri_style.upper()

    # Build output
    output_subs = pysubs2.SSAFile()
    output_subs.info = primary_subs.info.copy()

    # Copy existing styles and add bilingual ones
    for name, s in primary_subs.styles.items():
        output_subs.styles[name] = s
    add_bilingual_styles(output_subs, pri_style.upper(), sec_style.upper())

    # Merge events
    output_subs.events = merge_bilingual_events(pri_events, timed_secondary, style)

    save_subtitles(output_subs, output_path)
    return output_path
