"""Tests for the DP sequence matcher."""

from subalign.core.asr import Segment, WordSegment
from subalign.core.matcher import (
    MatchStatus,
    _align_sequences,
    _fuzzy_match_score,
    generate_alignment_report,
)


def _seg(text: str, start: float, end: float) -> Segment:
    return Segment(
        text=text, start=start, end=end,
        words=[], confidence=0.9,
    )


class TestFuzzyMatch:
    def test_identical(self):
        assert _fuzzy_match_score("hello world", "hello world") == 100.0

    def test_similar(self):
        score = _fuzzy_match_score("hello world", "hello worl")
        assert score > 80

    def test_different(self):
        score = _fuzzy_match_score("hello", "goodbye")
        assert score < 50

    def test_empty(self):
        assert _fuzzy_match_score("", "hello") == 0.0
        assert _fuzzy_match_score("hello", "") == 0.0


class TestAlignSequences:
    def test_perfect_match(self):
        sub_lines = ["Hello", "World"]
        asr_segments = [_seg("Hello", 0, 1), _seg("World", 1, 2)]
        results = _align_sequences(sub_lines, asr_segments)
        matched = [r for r in results if r.status == MatchStatus.MATCHED]
        assert len(matched) == 2

    def test_missing_in_sub(self):
        sub_lines = ["Hello"]
        asr_segments = [_seg("Hello", 0, 1), _seg("Extra line", 1, 2)]
        results = _align_sequences(sub_lines, asr_segments)
        missing = [r for r in results if r.status == MatchStatus.MISSING_IN_SUB]
        assert len(missing) >= 1

    def test_missing_in_asr(self):
        sub_lines = ["Hello", "This line has no audio"]
        asr_segments = [_seg("Hello", 0, 1)]
        results = _align_sequences(sub_lines, asr_segments)
        missing = [r for r in results if r.status == MatchStatus.MISSING_IN_ASR]
        assert len(missing) >= 1

    def test_empty_inputs(self):
        assert _align_sequences([], []) == []

    def test_timestamps_assigned(self):
        sub_lines = ["Test line"]
        asr_segments = [_seg("Test line", 5.0, 7.5)]
        results = _align_sequences(sub_lines, asr_segments)
        assert results[0].start_ms == 5000
        assert results[0].end_ms == 7500


class TestAlignmentReport:
    def test_report_structure(self):
        from subalign.core.matcher import MatchResult
        matches = [
            MatchResult(0, 0, MatchStatus.MATCHED, 0.95, "A", "A", 0, 1000),
            MatchResult(1, 1, MatchStatus.LOW_CONFIDENCE, 0.4, "B", "C", 1000, 2000),
            MatchResult(None, 2, MatchStatus.MISSING_IN_SUB, 0.9, "", "D", 2000, 3000),
        ]
        report = generate_alignment_report(matches)
        assert report["total_alignments"] == 3
        assert report["matched"] == 1
        assert report["low_confidence"] == 1
        assert report["missing_in_subtitle"] == 1
        assert 0 < report["average_confidence"] < 1
