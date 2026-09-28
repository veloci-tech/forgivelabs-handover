"""Text-to-Speech provider abstraction.

Supports Google Cloud TTS and ElevenLabs, with automatic fallback to stub
mode when credentials are unavailable.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TTSResult:
    """Result returned by a TTS provider."""

    audio_bytes: bytes
    audio_format: str = "mp3"
    sample_rate: int = 24000
    audio_url: str | None = None
    is_stub: bool = False


class TTSProvider(ABC):
    """Abstract interface for text-to-speech providers."""

    @abstractmethod
    def synthesize(self, text: str, *, voice: str | None = None, language: str = "en-US") -> TTSResult:
        """Convert text to speech audio.

        Args:
            text: Text to synthesize.
            voice: Provider-specific voice identifier.
            language: BCP-47 language code.

        Returns:
            TTSResult with audio data.
        """


class GoogleTTS(TTSProvider):
    """Google Cloud Text-to-Speech implementation.

    Falls back to a stub (empty audio) when credentials are missing.
    """

    DEFAULT_VOICE = "en-US-Neural2-F"

    def __init__(self) -> None:
        self._client = None
        try:
            from google.cloud import texttospeech  # type: ignore[import-untyped]
            self._client = texttospeech.TextToSpeechClient()
            self._tts = texttospeech
            logger.info("GoogleTTS initialised with live credentials.")
        except Exception:
            logger.warning("Google TTS credentials unavailable — running in stub mode.")

    def synthesize(self, text: str, *, voice: str | None = None, language: str = "en-US") -> TTSResult:
        if self._client is None:
            return self._stub_synthesize(text)

        try:
            synthesis_input = self._tts.SynthesisInput(text=text)
            voice_params = self._tts.VoiceSelectionParams(
                language_code=language,
                name=voice or self.DEFAULT_VOICE,
            )
            audio_config = self._tts.AudioConfig(
                audio_encoding=self._tts.AudioEncoding.MP3,
                sample_rate_hertz=24000,
            )
            response = self._client.synthesize_speech(
                input=synthesis_input,
                voice=voice_params,
                audio_config=audio_config,
            )
            return TTSResult(
                audio_bytes=response.audio_content,
                audio_format="mp3",
                sample_rate=24000,
            )
        except Exception as exc:
            logger.error("GoogleTTS synthesis failed: %s", exc)
            return self._stub_synthesize(text)

    @staticmethod
    def _stub_synthesize(text: str) -> TTSResult:
        logger.info("GoogleTTS returning stub audio (empty bytes).")
        return TTSResult(
            audio_bytes=b"",
            audio_format="mp3",
            sample_rate=24000,
            audio_url="stub://tts/google",
            is_stub=True,
        )


class ElevenLabsTTS(TTSProvider):
    """ElevenLabs TTS placeholder.

    Will be implemented when ElevenLabs integration is prioritised.
    """

    DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel

    def __init__(self) -> None:
        self._api_key = os.getenv("ELEVENLABS_API_KEY")
        if not self._api_key:
            logger.warning("ElevenLabs API key unavailable — running in stub mode.")

    def synthesize(self, text: str, *, voice: str | None = None, language: str = "en-US") -> TTSResult:
        if not self._api_key:
            return self._stub_synthesize(text)

        # TODO: implement ElevenLabs v1 TTS API call
        logger.info("ElevenLabsTTS live synthesis not yet implemented.")
        return self._stub_synthesize(text)

    @staticmethod
    def _stub_synthesize(text: str) -> TTSResult:
        logger.info("ElevenLabsTTS returning stub audio (empty bytes).")
        return TTSResult(
            audio_bytes=b"",
            audio_format="mp3",
            sample_rate=24000,
            audio_url="stub://tts/elevenlabs",
            is_stub=True,
        )


def get_tts_provider(provider: str | None = None) -> TTSProvider:
    """Factory: return the configured TTS provider.

    Args:
        provider: Explicit provider name ('google', 'elevenlabs').
                  Defaults to the ``TTS_PROVIDER`` env var, then ``'google'``.

    Returns:
        An initialised TTSProvider instance.
    """
    name = (provider or os.getenv("TTS_PROVIDER", "google")).lower()
    if name == "elevenlabs":
        return ElevenLabsTTS()
    return GoogleTTS()
