"""Subtitle parsing, format detection, and generation via pysubs2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import pysubs2


class SubtitleStatus(Enum):
    """Classification of subtitle timing status."""
    TIMED_OK = auto()       # S1: has timing, likely correct
    TIMED_SHIFTED = auto()  # S2: has timing but may be offset
    UNTIMED = auto()        # S3: no timing / plain text
    PARTIAL = auto()        # S3: some lines timed, some not


@dataclass
class SubtitleInfo:
    """Metadata about a loaded subtitle file."""
    path: Path
    format: str           # ass, srt, vtt, txt
    line_count: int
    timed_count: int      # lines with non-zero timing
    status: SubtitleStatus
    languages: list[str]  # detected/declared languages
    styles: list[str]     # ASS style names


def load_subtitles(path: Path) -> pysubs2.SSAFile:
    """Load subtitle file in any supported format.

    Plain text files are treated as one-line-per-subtitle with no timing.
    """
    path = Path(path)
    ext = path.suffix.lower()

    if ext == ".txt":
        return _load_plain_text(path)

    return pysubs2.load(str(path))


def _load_plain_text(path: Path) -> pysubs2.SSAFile:
    """Convert plain text file to SSAFile with zero timestamps."""
    subs = pysubs2.SSAFile()
    lines = path.read_text(encoding="utf-8").splitlines()

    for line in lines:
        line = line.strip()
        if not line:
            continue
        event = pysubs2.SSAEvent(
            start=0,
            end=0,
            text=line,
        )
        subs.events.append(event)

    return subs


def analyze_subtitles(subs: pysubs2.SSAFile, path: Path | None = None) -> SubtitleInfo:
    """Analyze subtitle file to determine its status and metadata."""
    dialogue_events = [e for e in subs.events if e.type == "Dialogue"]
    total = len(dialogue_events)
    timed = sum(1 for e in dialogue_events if e.start > 0 or e.end > 0)

    if total == 0:
        status = SubtitleStatus.UNTIMED
    elif timed == 0:
        status = SubtitleStatus.UNTIMED
    elif timed < total * 0.5:
        status = SubtitleStatus.PARTIAL
    else:
        status = SubtitleStatus.TIMED_OK

    fmt = "ass"
    if path:
        ext = Path(path).suffix.lower()
        fmt = {"srt": "srt", ".srt": "srt", ".vtt": "vtt", ".ass": "ass",
               ".ssa": "ssa", ".txt": "txt"}.get(ext, "ass")

    styles = [s.name for s in subs.styles.values()] if hasattr(subs, "styles") else []

    return SubtitleInfo(
        path=path or Path("unknown"),
        format=fmt,
        line_count=total,
        timed_count=timed,
        status=status,
        languages=[],
        styles=styles,
    )


def save_subtitles(subs: pysubs2.SSAFile, path: Path, format: str | None = None):
    """Save subtitle file. Format auto-detected from extension if not specified."""
    path = Path(path)
    if format:
        subs.save(str(path), format_=format)
    else:
        subs.save(str(path))


def get_dialogue_events(subs: pysubs2.SSAFile) -> list[pysubs2.SSAEvent]:
    """Get only Dialogue (non-comment) events."""
    return [e for e in subs.events if e.type == "Dialogue"]


def get_plain_text_lines(subs: pysubs2.SSAFile) -> list[str]:
    """Extract plain text from subtitle events, stripping ASS tags."""
    import re
    tag_re = re.compile(r"\{[^}]*\}")
    lines = []
    for event in get_dialogue_events(subs):
        text = tag_re.sub("", event.text)
        text = text.replace("\\N", "\n").replace("\\n", "\n")
        lines.append(text.strip())
    return lines


def add_bilingual_styles(subs: pysubs2.SSAFile, primary_name: str = "JP", secondary_name: str = "CN"):
    """Add bilingual styles to ASS file if not already present."""
    if primary_name not in subs.styles:
        primary = pysubs2.SSAStyle()
        primary.fontsize = 20
        primary.alignment = 8  # top center
        subs.styles[primary_name] = primary

    if secondary_name not in subs.styles:
        secondary = pysubs2.SSAStyle()
        secondary.fontsize = 18
        secondary.alignment = 2  # bottom center
        subs.styles[secondary_name] = secondary


def merge_bilingual_events(
    primary_events: list[pysubs2.SSAEvent],
    secondary_events: list[pysubs2.SSAEvent],
    style: str = "merged",
) -> list[pysubs2.SSAEvent]:
    """Merge two sets of timed events into bilingual lines.

    style: 'merged' combines with \\N, 'split' keeps separate with styles,
           'comment' adds secondary as Comment lines.
    """
    merged = []

    if style == "merged":
        for pri, sec in zip(primary_events, secondary_events):
            event = pysubs2.SSAEvent(
                start=pri.start,
                end=pri.end,
                text=f"{pri.text}\\N{sec.text}",
                style=pri.style,
            )
            merged.append(event)

    elif style == "split":
        for pri in primary_events:
            merged.append(pri)
        for sec in secondary_events:
            merged.append(sec)
        merged.sort(key=lambda e: e.start)

    elif style == "comment":
        for pri in primary_events:
            merged.append(pri)
        for sec in secondary_events:
            event = pysubs2.SSAEvent(
                start=sec.start,
                end=sec.end,
                text=sec.text,
                style=sec.style,
                type="Comment",
            )
            merged.append(event)
        merged.sort(key=lambda e: (e.start, e.type != "Dialogue"))

    return merged
