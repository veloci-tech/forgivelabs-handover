"""Speech-to-Text provider abstraction.

Supports Google Cloud Speech-to-Text and Deepgram, with automatic fallback
to stub mode when credentials are unavailable.
"""

from __future__ import annotations

import base64
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TranscriptResult:
    """Result returned by an STT provider."""

    text: str
    confidence: float
    language: str = "en-US"
    is_stub: bool = False


class STTProvider(ABC):
    """Abstract interface for speech-to-text providers."""

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, *, sample_rate: int = 16000, language: str = "en-US") -> TranscriptResult:
        """Transcribe raw audio bytes into text.

        Args:
            audio_bytes: Raw audio data (LINEAR16 / WAV).
            sample_rate: Audio sample rate in Hz.
            language: BCP-47 language code.

        Returns:
            TranscriptResult with the transcription.
        """


class GoogleSTT(STTProvider):
    """Google Cloud Speech-to-Text implementation.

    Falls back to a stub response when credentials are missing.
    """

    def __init__(self) -> None:
        self._client = None
        try:
            from google.cloud import speech  # type: ignore[import-untyped]
            self._client = speech.SpeechClient()
            self._speech = speech
            logger.info("GoogleSTT initialised with live credentials.")
        except Exception:
            logger.warning("Google Speech credentials unavailable — running in stub mode.")

    def transcribe(self, audio_bytes: bytes, *, sample_rate: int = 16000, language: str = "en-US") -> TranscriptResult:
        if self._client is None:
            return self._stub_transcribe()

        try:
            audio = self._speech.RecognitionAudio(content=audio_bytes)
            config = self._speech.RecognitionConfig(
                encoding=self._speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=sample_rate,
                language_code=language,
            )
            response = self._client.recognize(config=config, audio=audio)
            if response.results:
                best = response.results[0].alternatives[0]
                return TranscriptResult(
                    text=best.transcript,
                    confidence=best.confidence,
                    language=language,
                )
            return TranscriptResult(text="", confidence=0.0, language=language)
        except Exception as exc:
            logger.error("GoogleSTT transcription failed: %s", exc)
            return self._stub_transcribe()

    @staticmethod
    def _stub_transcribe() -> TranscriptResult:
        logger.info("GoogleSTT returning stub transcript.")
        return TranscriptResult(
            text="Hello, I need help understanding my treatment options.",
            confidence=0.95,
            language="en-US",
            is_stub=True,
        )


class DeepgramSTT(STTProvider):
    """Deepgram STT placeholder.

    Will be implemented when Deepgram integration is prioritised.
    """

    def __init__(self) -> None:
        self._api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self._api_key:
            logger.warning("Deepgram API key unavailable — running in stub mode.")

    def transcribe(self, audio_bytes: bytes, *, sample_rate: int = 16000, language: str = "en-US") -> TranscriptResult:
        if not self._api_key:
            return self._stub_transcribe()

        # TODO: implement Deepgram Nova-2 API call
        logger.info("DeepgramSTT live transcription not yet implemented.")
        return self._stub_transcribe()

    @staticmethod
    def _stub_transcribe() -> TranscriptResult:
        logger.info("DeepgramSTT returning stub transcript.")
        return TranscriptResult(
            text="Hello, I need help understanding my treatment options.",
            confidence=0.92,
            language="en-US",
            is_stub=True,
        )


def get_stt_provider(provider: str | None = None) -> STTProvider:
    """Factory: return the configured STT provider.

    Args:
        provider: Explicit provider name ('google', 'deepgram').
                  Defaults to the ``STT_PROVIDER`` env var, then ``'google'``.

    Returns:
        An initialised STTProvider instance.
    """
    name = (provider or os.getenv("STT_PROVIDER", "google")).lower()
    if name == "deepgram":
        return DeepgramSTT()
    return GoogleSTT()
