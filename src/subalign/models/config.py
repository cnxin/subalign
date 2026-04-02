"""Whisper model configuration and defaults."""

from dataclasses import dataclass, field
from pathlib import Path

WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3")
DEFAULT_MODEL = "medium"
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CONFIDENCE_THRESHOLD = 0.7

# Episode duration constraints for BD splitting (seconds)
MIN_EPISODE_DURATION = 1200  # 20 min
MAX_EPISODE_DURATION = 1800  # 30 min
DEFAULT_EPISODE_DURATION = (23 * 60, 25 * 60)  # 23-25 min typical anime

SUPPORTED_SUBTITLE_FORMATS = (".ass", ".ssa", ".srt", ".vtt", ".txt")
SUPPORTED_VIDEO_FORMATS = (".mkv", ".mp4", ".m2ts", ".avi", ".webm", ".flv")


@dataclass
class AlignConfig:
    """Configuration for alignment operations."""

    model_size: str = DEFAULT_MODEL
    language: str | None = None  # None = auto-detect
    device: str = "auto"  # auto / cuda / cpu
    compute_type: str = "auto"
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    sample_rate: int = DEFAULT_SAMPLE_RATE

    # Audio extraction
    audio_track: int | None = None  # None = default track

    # BD splitting
    ep_duration_range: tuple[int, int] = DEFAULT_EPISODE_DURATION
    silence_min_duration: float = 3.0
    silence_threshold: float = -50.0  # dB
    black_min_duration: float = 1.0

    # Bilingual
    bilingual_style: str = "split"  # split / merged / comment
    primary_lang: str | None = None
    secondary_lang: str | None = None

    # Output
    output_format: str = "ass"

    # Cache
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "subalign")

    def resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
