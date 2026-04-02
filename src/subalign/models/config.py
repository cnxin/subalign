"""Whisper model configuration and defaults."""

from __future__ import annotations

import json
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

# Language code → Chinese display name
LANG_NAMES = {
    "auto": "自动检测",
    "ja": "日语",
    "en": "英语",
    "zh": "中文",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "pt": "葡萄牙语",
    "it": "意大利语",
    "ar": "阿拉伯语",
    "th": "泰语",
    "vi": "越南语",
}

# Model display names
MODEL_NAMES = {
    "tiny": "极速 (tiny, ~75MB)",
    "base": "基础 (base, ~150MB)",
    "small": "标准 (small, ~500MB)",
    "medium": "推荐 (medium, ~1.5GB)",
    "large-v3": "最佳 (large-v3, ~3GB)",
}

# ASR backend options
ASR_BACKENDS = ("local", "openai", "azure", "aliyun")


def lang_display(code: str | None) -> str:
    """Get Chinese display name for a language code."""
    if code is None:
        return "自动检测"
    return LANG_NAMES.get(code, code)


def model_display(model: str) -> str:
    """Get display name for a model."""
    return MODEL_NAMES.get(model, model)


# --- Config file management ---

CONFIG_DIR = Path.home() / ".config" / "subalign"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "asr_backend": "local",       # local / openai / azure / aliyun
    "openai_api_key": "",
    "openai_base_url": "",        # 留空用官方，填写自定义兼容端点
    "openai_model": "whisper-1",
    "azure_api_key": "",
    "azure_region": "",
    "aliyun_appkey": "",
    "aliyun_access_key_id": "",
    "aliyun_access_key_secret": "",
    "local_model": "medium",
    "local_device": "auto",
    "default_language": None,
    "cache_dir": str(Path.home() / ".cache" / "subalign"),
}


def load_user_config() -> dict:
    """Load user config from ~/.config/subalign/config.json."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                user = json.load(f)
            # Merge with defaults (fill missing keys)
            merged = {**DEFAULT_CONFIG, **user}
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_CONFIG)


def save_user_config(config: dict):
    """Save user config to ~/.config/subalign/config.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


@dataclass
class AlignConfig:
    """Configuration for alignment operations."""

    model_size: str = DEFAULT_MODEL
    language: str | None = None  # None = auto-detect
    device: str = "auto"  # auto / cuda / cpu
    compute_type: str = "auto"
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    sample_rate: int = DEFAULT_SAMPLE_RATE

    # ASR backend
    asr_backend: str = "local"  # local / openai / azure / aliyun
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "whisper-1"

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

    @classmethod
    def from_user_config(cls, overrides: dict | None = None) -> "AlignConfig":
        """Create AlignConfig merging user config file + CLI overrides."""
        user = load_user_config()
        kwargs: dict = {}
        if user.get("local_model"):
            kwargs["model_size"] = user["local_model"]
        if user.get("local_device"):
            kwargs["device"] = user["local_device"]
        if user.get("default_language"):
            kwargs["language"] = user["default_language"]
        if user.get("asr_backend"):
            kwargs["asr_backend"] = user["asr_backend"]
        if user.get("openai_api_key"):
            kwargs["openai_api_key"] = user["openai_api_key"]
        if user.get("openai_base_url"):
            kwargs["openai_base_url"] = user["openai_base_url"]
        if user.get("openai_model"):
            kwargs["openai_model"] = user["openai_model"]
        if user.get("cache_dir"):
            kwargs["cache_dir"] = Path(user["cache_dir"])
        # CLI overrides take priority
        if overrides:
            kwargs.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**kwargs)
