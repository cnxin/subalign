"""Tests for AlignConfig."""

from subalign.models.config import AlignConfig, DEFAULT_MODEL


class TestAlignConfig:
    def test_defaults(self):
        config = AlignConfig()
        assert config.model_size == DEFAULT_MODEL
        assert config.language is None
        assert config.device == "auto"
        assert config.confidence_threshold == 0.7
        assert config.output_format == "ass"

    def test_custom_values(self):
        config = AlignConfig(
            model_size="large-v3",
            language="ja",
            device="cpu",
            bilingual_style="merged",
            primary_lang="ja",
            secondary_lang="zh",
        )
        assert config.model_size == "large-v3"
        assert config.language == "ja"
        assert config.bilingual_style == "merged"

    def test_resolve_device_explicit(self):
        config = AlignConfig(device="cpu")
        assert config.resolve_device() == "cpu"

    def test_resolve_device_auto_no_torch(self):
        config = AlignConfig(device="auto")
        # Without torch installed, should fall back to cpu
        device = config.resolve_device()
        assert device in ("cuda", "cpu")

    def test_ep_duration_range(self):
        config = AlignConfig()
        min_ep, max_ep = config.ep_duration_range
        assert min_ep == 23 * 60
        assert max_ep == 25 * 60
