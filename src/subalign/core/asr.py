"""ASR engine wrapper for faster-whisper and WhisperX."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from subalign.models.config import AlignConfig

if TYPE_CHECKING:
    pass


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
    """Unified ASR interface supporting faster-whisper and WhisperX."""

    def __init__(self, config: AlignConfig):
        self.config = config
        self._model = None
        self._backend: str | None = None

    def _load_whisperx(self):
        import whisperx
        device = self.config.resolve_device()
        compute_type = self.config.compute_type
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        self._model = whisperx.load_model(
            self.config.model_size,
            device=device,
            compute_type=compute_type,
            language=self.config.language,
        )
        self._backend = "whisperx"

    def _load_faster_whisper(self):
        from faster_whisper import WhisperModel
        device = self.config.resolve_device()
        compute_type = self.config.compute_type
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"
        self._model = WhisperModel(
            self.config.model_size,
            device=device,
            compute_type=compute_type,
        )
        self._backend = "faster_whisper"

    def load(self, prefer_whisperx: bool = True):
        """Load the ASR model. Prefers WhisperX for word-level alignment."""
        if self._model is not None:
            return

        if prefer_whisperx:
            try:
                self._load_whisperx()
                return
            except ImportError:
                pass

        self._load_faster_whisper()

    def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Transcribe audio file and return segments with word-level timestamps."""
        self.load()

        if self._backend == "whisperx":
            return self._transcribe_whisperx(audio_path)
        return self._transcribe_faster_whisper(audio_path)

    def _transcribe_whisperx(self, audio_path: Path) -> TranscriptionResult:
        import whisperx

        device = self.config.resolve_device()
        audio = whisperx.load_audio(str(audio_path))
        result = self._model.transcribe(audio, batch_size=16)

        detected_lang = result.get("language", self.config.language or "en")

        # Word-level alignment
        align_model, align_metadata = whisperx.load_align_model(
            language_code=detected_lang,
            device=device,
        )
        result = whisperx.align(
            result["segments"],
            align_model,
            align_metadata,
            audio,
            device,
            return_char_alignments=False,
        )

        segments = []
        for seg in result["segments"]:
            words = [
                WordSegment(
                    word=w["word"],
                    start=w["start"],
                    end=w["end"],
                    confidence=w.get("score", 1.0),
                )
                for w in seg.get("words", [])
                if "start" in w and "end" in w
            ]
            segments.append(Segment(
                text=seg["text"].strip(),
                start=seg["start"],
                end=seg["end"],
                words=words,
                language=detected_lang,
                confidence=min((w.confidence for w in words), default=1.0),
            ))

        duration = len(audio) / self.config.sample_rate
        return TranscriptionResult(
            segments=segments,
            language=detected_lang,
            duration=duration,
        )

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
                    word=w.word,
                    start=w.start,
                    end=w.end,
                    confidence=w.probability,
                )
                for w in (seg.words or [])
            ]
            segments.append(Segment(
                text=seg.text.strip(),
                start=seg.start,
                end=seg.end,
                words=words,
                language=detected_lang,
                confidence=min((w.confidence for w in words), default=1.0),
            ))

        return TranscriptionResult(
            segments=segments,
            language=detected_lang,
            duration=info.duration,
        )


def transcribe_audio(audio_path: Path, config: AlignConfig) -> TranscriptionResult:
    """Convenience function to transcribe an audio file."""
    engine = ASREngine(config)
    return engine.transcribe(audio_path)
