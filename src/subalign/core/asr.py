"""ASR engine wrapper for faster-whisper, WhisperX, and OpenAI API."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from subalign.models.config import AlignConfig


def _default_progress(msg: str):
    print(msg, file=sys.stderr, flush=True)


@dataclass
class WordSegment:
    """A single word with timestamp and confidence."""
    word: str
    start: float
    end: float
    confidence: float = 1.0


@dataclass
class Segment:
    """A transcribed segment (sentence/phrase)."""
    text: str
    start: float
    end: float
    words: list[WordSegment]
    language: str | None = None
    confidence: float = 1.0


@dataclass
class TranscriptionResult:
    """Full transcription output."""
    segments: list[Segment]
    language: str
    duration: float


class ASREngine:
    """Unified ASR interface: local (faster-whisper/WhisperX) + online (OpenAI API)."""

    def __init__(self, config: AlignConfig, on_progress: Callable[[str], None] | None = None):
        self.config = config
        self._model = None
        self._backend: str | None = None
        self._progress = on_progress or _default_progress

    # ── Model loading ──────────────────────────────────────

    def _load_whisperx(self):
        import whisperx
        device = self.config.resolve_device()
        compute_type = self.config.compute_type
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        self._progress(f"加载 WhisperX 模型 ({self.config.model_size})，首次运行需下载...")
        self._model = whisperx.load_model(
            self.config.model_size,
            device=device,
            compute_type=compute_type,
            language=self.config.language,
        )
        self._progress("WhisperX 模型加载完成")
        self._backend = "whisperx"

    def _load_faster_whisper(self):
        from faster_whisper import WhisperModel
        device = self.config.resolve_device()
        compute_type = self.config.compute_type
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        self._progress(f"加载 faster-whisper 模型 ({self.config.model_size})，首次运行需下载...")
        self._model = WhisperModel(
            self.config.model_size,
            device=device,
            compute_type=compute_type,
        )
        self._progress("faster-whisper 模型加载完成")
        self._backend = "faster_whisper"

    def load(self, prefer_whisperx: bool = True):
        """Load the ASR model or configure online backend."""
        if self._model is not None or self._backend is not None:
            return

        # Online backends: no model to load
        if self.config.asr_backend == "openai":
            self._backend = "openai"
            self._progress("使用 OpenAI Whisper API（在线模式）")
            return

        # Local backends
        if prefer_whisperx:
            try:
                self._load_whisperx()
                return
            except ImportError:
                pass

        self._load_faster_whisper()

    # ── Transcription dispatch ─────────────────────────────

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe audio file and return segments with word-level timestamps."""
        self.load()
        self._progress(f"开始转录: {Path(audio_path).name}")

        if self._backend == "openai":
            result = self._transcribe_openai(audio_path)
        elif self._backend == "whisperx":
            result = self._transcribe_whisperx(audio_path)
        else:
            result = self._transcribe_faster_whisper(audio_path)

        self._progress(f"转录完成: {len(result.segments)} 段, 语言={result.language}")
        return result

    # ── OpenAI Whisper API ─────────────────────────────────

    def _transcribe_openai(self, audio_path: Path) -> TranscriptionResult:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "使用 OpenAI API 需要安装 openai 库: pip install openai"
            )

        api_key = self.config.openai_api_key
        if not api_key:
            raise ValueError(
                "未配置 OpenAI API Key。\n"
                "请运行 subalign config 设置，或编辑 ~/.config/subalign/config.json"
            )

        client_kwargs = {"api_key": api_key}
        if self.config.openai_base_url:
            client_kwargs["base_url"] = self.config.openai_base_url

        client = OpenAI(**client_kwargs)

        # OpenAI API has 25MB limit; split large files
        file_size = Path(audio_path).stat().st_size
        if file_size > 24 * 1024 * 1024:
            return self._transcribe_openai_chunked(client, audio_path)

        self._progress("上传音频到 API...")

        with open(audio_path, "rb") as f:
            kwargs = {
                "model": self.config.openai_model,
                "file": f,
                "response_format": "verbose_json",
                "timestamp_granularities": ["word", "segment"],
            }
            if self.config.language:
                kwargs["language"] = self.config.language
            response = client.audio.transcriptions.create(**kwargs)

        return self._parse_openai_response(response)

    def _transcribe_openai_chunked(self, client, audio_path: Path) -> TranscriptionResult:
        from subalign.core.audio import get_video_duration

        self._progress("音频文件较大，分段上传中...")
        duration = get_video_duration(audio_path)
        chunk_sec = 600  # 10 min chunks
        all_segments = []
        detected_lang = self.config.language or "en"
        offset = 0.0
        chunk_idx = 0

        while offset < duration:
            chunk_idx += 1
            end = min(offset + chunk_sec, duration)
            self._progress(f"分段转录 {chunk_idx}: {offset:.0f}s - {end:.0f}s")

            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp_path = tmp.name
            tmp.close()

            subprocess.run([
                "ffmpeg", "-y", "-i", str(audio_path),
                "-ss", str(offset), "-t", str(chunk_sec),
                "-ac", "1", "-ar", "16000", tmp_path,
            ], capture_output=True, check=True)

            with open(tmp_path, "rb") as f:
                kwargs = {
                    "model": self.config.openai_model,
                    "file": f,
                    "response_format": "verbose_json",
                    "timestamp_granularities": ["word", "segment"],
                }
                if self.config.language:
                    kwargs["language"] = self.config.language
                response = client.audio.transcriptions.create(**kwargs)

            Path(tmp_path).unlink(missing_ok=True)

            chunk_result = self._parse_openai_response(response)
            detected_lang = chunk_result.language
            for seg in chunk_result.segments:
                seg.start += offset
                seg.end += offset
                for w in seg.words:
                    w.start += offset
                    w.end += offset
                all_segments.append(seg)

            offset = end

        return TranscriptionResult(segments=all_segments, language=detected_lang, duration=duration)

    def _parse_openai_response(self, response) -> TranscriptionResult:
        detected_lang = getattr(response, "language", self.config.language or "en")
        api_words = getattr(response, "words", []) or []
        word_idx = 0
        segments = []

        for seg_data in getattr(response, "segments", []):
            seg_start = seg_data.get("start", 0)
            seg_end = seg_data.get("end", seg_start)
            seg_text = seg_data.get("text", "").strip()

            seg_words = []
            while word_idx < len(api_words):
                w = api_words[word_idx]
                w_start = w.get("start", 0)
                w_end = w.get("end", w_start)
                if w_start > seg_end + 0.5:
                    break
                seg_words.append(WordSegment(
                    word=w.get("word", ""),
                    start=w_start, end=w_end, confidence=1.0,
                ))
                word_idx += 1

            segments.append(Segment(
                text=seg_text, start=seg_start, end=seg_end,
                words=seg_words, language=detected_lang, confidence=1.0,
            ))

        duration = segments[-1].end if segments else 0
        return TranscriptionResult(segments=segments, language=detected_lang, duration=duration)

    # ── WhisperX (local) ───────────────────────────────────

    def _transcribe_whisperx(self, audio_path: Path) -> TranscriptionResult:
        import whisperx

        device = self.config.resolve_device()
        audio = whisperx.load_audio(str(audio_path))
        result = self._model.transcribe(audio, batch_size=16)

        detected_lang = result.get("language", self.config.language or "en")

        align_model, align_metadata = whisperx.load_align_model(
            language_code=detected_lang, device=device,
        )
        result = whisperx.align(
            result["segments"], align_model, align_metadata,
            audio, device, return_char_alignments=False,
        )

        segments = []
        for seg in result["segments"]:
            words = [
                WordSegment(
                    word=w["word"], start=w["start"], end=w["end"],
                    confidence=w.get("score", 1.0),
                )
                for w in seg.get("words", [])
                if "start" in w and "end" in w
            ]
            segments.append(Segment(
                text=seg["text"].strip(), start=seg["start"], end=seg["end"],
                words=words, language=detected_lang,
                confidence=min((w.confidence for w in words), default=1.0),
            ))

        duration = len(audio) / self.config.sample_rate
        return TranscriptionResult(segments=segments, language=detected_lang, duration=duration)

    # ── faster-whisper (local) ─────────────────────────────

    def _transcribe_faster_whisper(self, audio_path: Path) -> TranscriptionResult:
        segments_iter, info = self._model.transcribe(
            str(audio_path),
            language=self.config.language,
            word_timestamps=True,
            vad_filter=True,
        )

        detected_lang = info.language
        segments = []

        for seg in segments_iter:
            words = [
                WordSegment(
                    word=w.word, start=w.start, end=w.end,
                    confidence=w.probability,
                )
                for w in (seg.words or [])
            ]
            segments.append(Segment(
                text=seg.text.strip(), start=seg.start, end=seg.end,
                words=words, language=detected_lang,
                confidence=min((w.confidence for w in words), default=1.0),
            ))

        return TranscriptionResult(segments=segments, language=detected_lang, duration=info.duration)


def transcribe_audio(audio_path: Path, config: AlignConfig) -> TranscriptionResult:
    """Convenience function to transcribe an audio file."""
    engine = ASREngine(config)
    return engine.transcribe(audio_path)
