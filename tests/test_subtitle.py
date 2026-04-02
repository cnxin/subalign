"""Tests for subtitle parsing and format detection."""

import pysubs2
import pytest

from subalign.core.subtitle import (
    SubtitleStatus,
    add_bilingual_styles,
    analyze_subtitles,
    get_dialogue_events,
    get_plain_text_lines,
    merge_bilingual_events,
)


def _make_subs(events: list[tuple[int, int, str]]) -> pysubs2.SSAFile:
    """Helper: create SSAFile from (start_ms, end_ms, text) tuples."""
    subs = pysubs2.SSAFile()
    for start, end, text in events:
        subs.events.append(pysubs2.SSAEvent(start=start, end=end, text=text))
    return subs


class TestAnalyzeSubtitles:
    def test_timed_ok(self):
        subs = _make_subs([
            (1000, 3000, "Hello"),
            (4000, 6000, "World"),
        ])
        info = analyze_subtitles(subs)
        assert info.status == SubtitleStatus.TIMED_OK
        assert info.line_count == 2
        assert info.timed_count == 2

    def test_untimed(self):
        subs = _make_subs([
            (0, 0, "Hello"),
            (0, 0, "World"),
        ])
        info = analyze_subtitles(subs)
        assert info.status == SubtitleStatus.UNTIMED
        assert info.timed_count == 0

    def test_partial(self):
        subs = _make_subs([
            (1000, 3000, "Timed line"),
            (0, 0, "Untimed line 1"),
            (0, 0, "Untimed line 2"),
            (0, 0, "Untimed line 3"),
        ])
        info = analyze_subtitles(subs)
        assert info.status == SubtitleStatus.PARTIAL
        assert info.timed_count == 1

    def test_empty(self):
        subs = pysubs2.SSAFile()
        info = analyze_subtitles(subs)
        assert info.status == SubtitleStatus.UNTIMED
        assert info.line_count == 0


class TestGetPlainText:
    def test_strip_tags(self):
        subs = _make_subs([
            (0, 0, r"{\b1}Bold text{\b0}"),
            (0, 0, r"{\c&H0000FF&}Colored"),
        ])
        lines = get_plain_text_lines(subs)
        assert lines == ["Bold text", "Colored"]

    def test_newline_replacement(self):
        subs = _make_subs([
            (0, 0, r"Line 1\NLine 2"),
        ])
        lines = get_plain_text_lines(subs)
        assert lines == ["Line 1\nLine 2"]

    def test_skip_comments(self):
        subs = pysubs2.SSAFile()
        subs.events.append(pysubs2.SSAEvent(start=0, end=0, text="Visible"))
        subs.events.append(pysubs2.SSAEvent(start=0, end=0, text="Hidden", type="Comment"))
        lines = get_plain_text_lines(subs)
        assert lines == ["Visible"]


class TestDialogueEvents:
    def test_filter_comments(self):
        subs = pysubs2.SSAFile()
        subs.events.append(pysubs2.SSAEvent(text="A"))
        subs.events.append(pysubs2.SSAEvent(text="B", type="Comment"))
        subs.events.append(pysubs2.SSAEvent(text="C"))
        events = get_dialogue_events(subs)
        assert len(events) == 2
        assert events[0].text == "A"
        assert events[1].text == "C"


class TestBilingualStyles:
    def test_add_styles(self):
        subs = pysubs2.SSAFile()
        add_bilingual_styles(subs, "JP", "CN")
        assert "JP" in subs.styles
        assert "CN" in subs.styles

    def test_no_overwrite(self):
        subs = pysubs2.SSAFile()
        custom = pysubs2.SSAStyle(fontsize=42)
        subs.styles["JP"] = custom
        add_bilingual_styles(subs, "JP", "CN")
        assert subs.styles["JP"].fontsize == 42  # not overwritten


class TestMergeBilingual:
    def _make_events(self, texts, start=0, step=2000):
        events = []
        for i, text in enumerate(texts):
            events.append(pysubs2.SSAEvent(
                start=start + i * step,
                end=start + (i + 1) * step,
                text=text,
                style="Default",
            ))
        return events

    def test_merged_style(self):
        pri = self._make_events(["こんにちは", "さようなら"])
        sec = self._make_events(["你好", "再见"])
        merged = merge_bilingual_events(pri, sec, "merged")
        assert len(merged) == 2
        assert r"\N" in merged[0].text

    def test_split_style(self):
        pri = self._make_events(["A", "B"])
        sec = self._make_events(["X", "Y"])
        merged = merge_bilingual_events(pri, sec, "split")
        assert len(merged) == 4

    def test_comment_style(self):
        pri = self._make_events(["A"])
        sec = self._make_events(["X"])
        merged = merge_bilingual_events(pri, sec, "comment")
        comments = [e for e in merged if e.type == "Comment"]
        assert len(comments) == 1
        assert comments[0].text == "X"
