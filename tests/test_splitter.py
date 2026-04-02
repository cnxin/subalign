"""Tests for BD episode splitting logic."""

from subalign.core.splitter import (
    EpisodeBoundary,
    _cross_validate_boundaries,
    _filter_by_duration,
    format_boundaries_report,
    SplitResult,
)


class TestCrossValidate:
    def test_silence_and_black_match(self):
        silences = [{"start": 1478, "end": 1483, "duration": 5}]
        blacks = [{"start": 1479, "end": 1482, "duration": 3}]
        candidates = _cross_validate_boundaries(silences, blacks)
        assert len(candidates) >= 1
        assert "silence" in candidates[0]["signals"]
        assert "black" in candidates[0]["signals"]
        assert candidates[0]["confidence"] >= 0.8

    def test_silence_only(self):
        silences = [{"start": 1478, "end": 1483, "duration": 5}]
        blacks = []
        candidates = _cross_validate_boundaries(silences, blacks)
        assert len(candidates) == 1
        assert candidates[0]["confidence"] < 0.8

    def test_no_signals(self):
        candidates = _cross_validate_boundaries([], [])
        assert candidates == []


class TestFilterByDuration:
    def test_standard_episodes(self):
        # 3 episodes at ~24min each = boundaries at ~1440s and ~2880s
        candidates = [
            {"time": 1440, "signals": ["silence", "black"], "confidence": 0.9},
            {"time": 2880, "signals": ["silence", "black"], "confidence": 0.9},
        ]
        filtered = _filter_by_duration(candidates, total_duration=4320, min_ep=1200, max_ep=1800)
        assert len(filtered) == 2

    def test_too_close_filtered(self):
        # Two candidates too close together (< min_ep apart)
        candidates = [
            {"time": 1440, "signals": ["silence"], "confidence": 0.5},
            {"time": 1500, "signals": ["black"], "confidence": 0.4},  # only 60s after
        ]
        filtered = _filter_by_duration(candidates, total_duration=4320, min_ep=1200, max_ep=1800)
        assert len(filtered) == 1

    def test_empty(self):
        assert _filter_by_duration([], 4320) == []


class TestFormatReport:
    def test_report_format(self):
        result = SplitResult(
            boundaries=[
                EpisodeBoundary(0, 1440, 0.9, ["silence", "black"]),
                EpisodeBoundary(1443, 2880, 0.9, ["silence", "black"]),
            ],
            total_duration=4320,
            episode_count=2,
        )
        text = format_boundaries_report(result)
        assert "EP01" in text
        assert "EP02" in text
        assert "2 episodes" in text or "Detected episodes: 2" in text
