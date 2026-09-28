"""Streaming voice-AI pipeline.

Chains STT -> Safety -> LLM -> Safety -> TTS with async generator support
and per-session state management.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

from pipeline.safety import SafetyResult, check_input_safety, check_output_safety
from pipeline.stt import STTProvider, TranscriptResult, get_stt_provider
from pipeline.llm import LLMProvider, LLMResponse, get_llm_provider
from pipeline.tts import TTSProvider, TTSResult, get_tts_provider

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """In-memory state for a single voice session."""

    session_id: str
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    turn_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def add_turn(self, role: str, content: str) -> None:
        self.conversation_history.append({"role": role, "content": content})
        self.turn_count += 1
        self.last_activity = time.time()


@dataclass
class PipelineChunk:
    """A single chunk emitted during streaming."""

    stage: str  # "stt" | "safety_in" | "llm" | "safety_out" | "tts"
    data: TranscriptResult | SafetyResult | LLMResponse | TTSResult | None = None
    error: str | None = None


class StreamingPipeline:
    """End-to-end voice AI pipeline with streaming support.

    Usage::

        pipeline = StreamingPipeline(session_id="abc123")
        async for chunk in pipeline.process(audio_bytes):
            handle(chunk)
    """

    def __init__(
        self,
        session_id: str,
        *,
        stt: STTProvider | None = None,
        llm: LLMProvider | None = None,
        tts: TTSProvider | None = None,
    ) -> None:
        self.stt = stt or get_stt_provider()
        self.llm = llm or get_llm_provider()
        self.tts = tts or get_tts_provider()
        self.state = SessionState(session_id=session_id)

    async def process(self, audio_bytes: bytes) -> AsyncIterator[PipelineChunk]:
        """Run the full pipeline on a single audio turn.

        Yields PipelineChunk objects for each stage so callers can stream
        partial results to the client.
        """

        # 1. Speech-to-Text
        try:
            transcript = await asyncio.to_thread(self.stt.transcribe, audio_bytes)
            yield PipelineChunk(stage="stt", data=transcript)
        except Exception as exc:
            logger.error("STT stage failed: %s", exc)
            yield PipelineChunk(stage="stt", error=str(exc))
            return

        if not transcript.text.strip():
            yield PipelineChunk(stage="stt", error="Empty transcript")
            return

        # 2. Input safety check
        try:
            input_safety = check_input_safety(transcript.text)
            yield PipelineChunk(stage="safety_in", data=input_safety)
        except Exception as exc:
            logger.error("Input safety check failed: %s", exc)
            yield PipelineChunk(stage="safety_in", error=str(exc))
            return

        if not input_safety.is_safe:
            logger.warning("Input flagged as unsafe: %s", input_safety.flags)
            yield PipelineChunk(
                stage="safety_in",
                error=f"Input blocked — flags: {input_safety.flags}",
            )
            return

        safe_input = input_safety.filtered_text
        self.state.add_turn("user", safe_input)

        # 3. LLM generation
        try:
            llm_response = await asyncio.to_thread(
                self.llm.generate,
                safe_input,
                conversation_history=self.state.conversation_history[:-1],
            )
            yield PipelineChunk(stage="llm", data=llm_response)
        except Exception as exc:
            logger.error("LLM stage failed: %s", exc)
            yield PipelineChunk(stage="llm", error=str(exc))
            return

        # 4. Output safety check
        try:
            output_safety = check_output_safety(llm_response.text)
            yield PipelineChunk(stage="safety_out", data=output_safety)
        except Exception as exc:
            logger.error("Output safety check failed: %s", exc)
            yield PipelineChunk(stage="safety_out", error=str(exc))
            return

        if not output_safety.is_safe:
            logger.warning("Output flagged as unsafe: %s", output_safety.flags)
            yield PipelineChunk(
                stage="safety_out",
                error=f"Output blocked — flags: {output_safety.flags}",
            )
            return

        safe_output = output_safety.filtered_text
        self.state.add_turn("assistant", safe_output)

        # 5. Text-to-Speech
        try:
            tts_result = await asyncio.to_thread(self.tts.synthesize, safe_output)
            yield PipelineChunk(stage="tts", data=tts_result)
        except Exception as exc:
            logger.error("TTS stage failed: %s", exc)
            yield PipelineChunk(stage="tts", error=str(exc))
