"""Full alignment with ASR text matching and missing segment detection (S3).

Core algorithm:
1. WhisperX full ASR → word-level transcription with timestamps
2. Sequence alignment between ASR text and existing subtitle text
3. Map subtitle lines to ASR time ranges
4. Detect missing/extra content
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import pysubs2
from rapidfuzz import fuzz

from subalign.core.asr import Segment, TranscriptionResult, transcribe_audio
from subalign.core.audio import extract_audio
from subalign.core.subtitle import get_plain_text_lines, load_subtitles, save_subtitles
from subalign.models.config import AlignConfig


class MatchStatus(Enum):
    MATCHED = auto()
    LOW_CONFIDENCE = auto()
    MISSING_IN_SUB = auto()   # ASR has it, subtitle doesn't
    MISSING_IN_ASR = auto()   # subtitle has it, ASR doesn't


@dataclass
class MatchResult:
    sub_index: int | None
    asr_index: int | None
    status: MatchStatus
    confidence: float
    sub_text: str
    asr_text: str
    start_ms: int
    end_ms: int


def _fuzzy_match_score(text_a: str, text_b: str) -> float:
    """Compute fuzzy match score between two texts (0-100)."""
    if not text_a or not text_b:
        return 0.0
    return fuzz.token_sort_ratio(text_a, text_b)


def _align_sequences(
    sub_lines: list[str],
    asr_segments: list[Segment],
    threshold: float = 50.0,
) -> list[MatchResult]:
    """Align subtitle lines to ASR segments using dynamic programming.

    Allows 1:1, 1:N, and N:1 mappings.
    """
    n = len(sub_lines)
    m = len(asr_segments)

    if n == 0 and m == 0:
        return []

    # Build cost matrix for DP
    INF = float("inf")
    # dp[i][j] = best score aligning sub_lines[:i] with asr_segments[:j]
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]

    # Penalties for skipping
    SKIP_PENALTY = -30.0

    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + SKIP_PENALTY
        back[i][0] = (i - 1, 0, "skip_sub")

    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] + SKIP_PENALTY
        back[0][j] = (0, j - 1, "skip_asr")

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            # Option 1: match sub[i-1] with asr[j-1]
            score = _fuzzy_match_score(sub_lines[i - 1], asr_segments[j - 1].text)
            match_val = dp[i - 1][j - 1] + score

            # Option 2: skip subtitle line (missing in ASR)
            skip_sub = dp[i - 1][j] + SKIP_PENALTY

            # Option 3: skip ASR segment (missing in subtitle)
            skip_asr = dp[i][j - 1] + SKIP_PENALTY

            # Option 4: merge two ASR segments into one subtitle line
            merge_asr = -INF
            if j >= 2:
                merged_text = asr_segments[j - 2].text + " " + asr_segments[j - 1].text
                merge_score = _fuzzy_match_score(sub_lines[i - 1], merged_text)
                merge_asr = dp[i - 1][j - 2] + merge_score

            best = max(match_val, skip_sub, skip_asr, merge_asr)
            dp[i][j] = best

            if best == match_val:
                back[i][j] = (i - 1, j - 1, "match")
            elif best == merge_asr:
                back[i][j] = (i - 1, j - 2, "merge_asr")
            elif best == skip_sub:
                back[i][j] = (i - 1, j, "skip_sub")
            else:
                back[i][j] = (i, j - 1, "skip_asr")

    # Traceback
    results: list[MatchResult] = []
    i, j = n, m

    while i > 0 or j > 0:
        if back[i][j] is None:
            break

        pi, pj, action = back[i][j]

        if action == "match":
            seg = asr_segments[j - 1]
            score = _fuzzy_match_score(sub_lines[i - 1], seg.text)
            status = MatchStatus.MATCHED if score >= threshold else MatchStatus.LOW_CONFIDENCE
            results.append(MatchResult(
                sub_index=i - 1,
                asr_index=j - 1,
                status=status,
                confidence=score / 100.0,
                sub_text=sub_lines[i - 1],
                asr_text=seg.text,
                start_ms=int(seg.start * 1000),
                end_ms=int(seg.end * 1000),
            ))

        elif action == "merge_asr":
            seg_a = asr_segments[j - 2]
            seg_b = asr_segments[j - 1]
            merged_text = seg_a.text + " " + seg_b.text
            score = _fuzzy_match_score(sub_lines[i - 1], merged_text)
            status = MatchStatus.MATCHED if score >= threshold else MatchStatus.LOW_CONFIDENCE
            results.append(MatchResult(
                sub_index=i - 1,
                asr_index=j - 2,
                status=status,
                confidence=score / 100.0,
                sub_text=sub_lines[i - 1],
                asr_text=merged_text,
                start_ms=int(seg_a.start * 1000),
                end_ms=int(seg_b.end * 1000),
            ))

        elif action == "skip_sub":
            results.append(MatchResult(
                sub_index=i - 1,
                asr_index=None,
                status=MatchStatus.MISSING_IN_ASR,
                confidence=0.0,
                sub_text=sub_lines[i - 1],
                asr_text="",
                start_ms=0,
                end_ms=0,
            ))

        elif action == "skip_asr":
            seg = asr_segments[j - 1]
            results.append(MatchResult(
                sub_index=None,
                asr_index=j - 1,
                status=MatchStatus.MISSING_IN_SUB,
                confidence=seg.confidence,
                sub_text="",
                asr_text=seg.text,
                start_ms=int(seg.start * 1000),
                end_ms=int(seg.end * 1000),
            ))

        i, j = pi, pj

    results.reverse()
    return results


def full_align(
    video_path: Path,
    subtitle_path: Path,
    output_path: Path,
    config: AlignConfig,
    detect_missing: bool = False,
) -> tuple[Path, list[MatchResult]]:
    """Full alignment pipeline for S3 scenario.

    Returns (output_path, match_results).
    """
    audio_path = extract_audio(video_path, config)
    asr_result = transcribe_audio(audio_path, config)

    subs = load_subtitles(subtitle_path)
    sub_lines = get_plain_text_lines(subs)
    dialogue = [e for e in subs.events if e.type == "Dialogue"]

    match_results = _align_sequences(sub_lines, asr_result.segments, config.confidence_threshold * 100)

    # Apply matched timestamps
    for result in match_results:
        if result.sub_index is not None and result.start_ms > 0:
            event = dialogue[result.sub_index]
            event.start = result.start_ms
            event.end = result.end_ms

            if result.status == MatchStatus.LOW_CONFIDENCE:
                # Mark low-confidence lines
                if not event.text.startswith("{\\c&H0000FF&}"):
                    event.text = "{\\c&H0000FF&}[?] " + event.text

    # Add missing segments as comments if detect_missing is enabled
    if detect_missing:
        for result in match_results:
            if result.status == MatchStatus.MISSING_IN_SUB and result.asr_text:
                comment = pysubs2.SSAEvent(
                    start=result.start_ms,
                    end=result.end_ms,
                    text=f"{{\\c&H00FF00&}}[ASR] {result.asr_text}",
                    type="Comment",
                )
                subs.events.append(comment)

        subs.events.sort(key=lambda e: e.start)

    save_subtitles(subs, output_path)
    return output_path, match_results


def generate_alignment_report(matches: list[MatchResult]) -> dict:
    """Generate a summary report of alignment results."""
    total = len(matches)
    matched = sum(1 for m in matches if m.status == MatchStatus.MATCHED)
    low_conf = sum(1 for m in matches if m.status == MatchStatus.LOW_CONFIDENCE)
    missing_sub = sum(1 for m in matches if m.status == MatchStatus.MISSING_IN_SUB)
    missing_asr = sum(1 for m in matches if m.status == MatchStatus.MISSING_IN_ASR)
    avg_conf = sum(m.confidence for m in matches) / total if total else 0

    return {
        "total_alignments": total,
        "matched": matched,
        "low_confidence": low_conf,
        "missing_in_subtitle": missing_sub,
        "missing_in_asr": missing_asr,
        "average_confidence": round(avg_conf, 3),
        "details": [
            {
                "sub_index": m.sub_index,
                "asr_index": m.asr_index,
                "status": m.status.name,
                "confidence": round(m.confidence, 3),
                "sub_text": m.sub_text[:80],
                "asr_text": m.asr_text[:80],
                "start_ms": m.start_ms,
                "end_ms": m.end_ms,
            }
            for m in matches
        ],
    }
