"""Mercy POC — Cloud Functions entry points.

Firebase Functions (2nd gen, Python) exposing the voice-AI pipeline:
  - process_voice: STT on uploaded audio
  - generate_response: safety-checked LLM completion
  - synthesize_speech: TTS from text
  - create_session / end_session: Firestore session lifecycle
  - get_metrics: aggregated session metrics
"""

from __future__ import annotations

import base64
import json
import logging
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

import firebase_admin  # type: ignore[import-untyped]
from firebase_admin import firestore  # type: ignore[import-untyped]
from firebase_functions import https_fn, options  # type: ignore[import-untyped]

from pipeline.stt import get_stt_provider
from pipeline.llm import get_llm_provider
from pipeline.tts import get_tts_provider
from pipeline.safety import check_input_safety, check_output_safety

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

firebase_admin.initialize_app()

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "3600",
}

CORS_OPTIONS = options.CorsOptions(cors_origins="*", cors_methods=["GET", "POST", "OPTIONS"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_db() -> Any:
    """Return Firestore client (lazy)."""
    return firestore.client()


def _json_response(data: dict[str, Any], status: int = 200) -> https_fn.Response:
    """Build a JSON response with CORS headers."""
    return https_fn.Response(
        json.dumps(data, default=str),
        status=status,
        headers={**_CORS_HEADERS, "Content-Type": "application/json"},
    )


def _error_response(message: str, status: int = 400) -> https_fn.Response:
    return _json_response({"error": message}, status=status)


def _parse_json_body(request: https_fn.Request) -> dict[str, Any] | None:
    """Safely parse JSON from the request body."""
    try:
        return request.get_json(silent=True) or {}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cloud Functions
# ---------------------------------------------------------------------------


@https_fn.on_request(cors=CORS_OPTIONS)
def process_voice(request: https_fn.Request) -> https_fn.Response:
    """Receive audio and return a transcript via STT.

    Expects JSON body::

        {
            "audio": "<base64-encoded audio bytes>",
            "sample_rate": 16000,       // optional
            "language": "en-US"         // optional
        }

    Returns::

        {
            "transcript": "...",
            "confidence": 0.95,
            "is_stub": false
        }
    """
    if request.method == "OPTIONS":
        return _json_response({})

    body = _parse_json_body(request)
    if body is None:
        return _error_response("Invalid JSON body")

    audio_b64: str | None = body.get("audio")
    if not audio_b64:
        return _error_response("Missing 'audio' field (base64-encoded)")

    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        return _error_response("Invalid base64 in 'audio' field")

    sample_rate = int(body.get("sample_rate", 16000))
    language = str(body.get("language", "en-US"))

    try:
        provider = get_stt_provider()
        result = provider.transcribe(audio_bytes, sample_rate=sample_rate, language=language)

        logger.info("STT result (stub=%s): %s", result.is_stub, result.text[:80])
        return _json_response({
            "transcript": result.text,
            "confidence": result.confidence,
            "language": result.language,
            "is_stub": result.is_stub,
        })
    except Exception as exc:
        logger.exception("process_voice failed")
        return _error_response(f"STT processing error: {exc}", status=500)


@https_fn.on_request(cors=CORS_OPTIONS)
def generate_response(request: https_fn.Request) -> https_fn.Response:
    """Take a transcript, run safety checks, call LLM, safety-check output.

    Expects JSON body::

        {
            "transcript": "user text",
            "session_id": "optional-session-id",
            "conversation_history": [...]   // optional
        }

    Returns::

        {
            "response": "...",
            "model": "...",
            "safety_flags_in": [...],
            "safety_flags_out": [...],
            "is_stub": false
        }
    """
    if request.method == "OPTIONS":
        return _json_response({})

    body = _parse_json_body(request)
    if body is None:
        return _error_response("Invalid JSON body")

    transcript: str | None = body.get("transcript")
    if not transcript or not transcript.strip():
        return _error_response("Missing or empty 'transcript' field")

    session_id: str | None = body.get("session_id")
    conversation_history: list[dict[str, str]] = body.get("conversation_history", [])

    # --- Input safety ---
    input_check = check_input_safety(transcript)
    if not input_check.is_safe:
        logger.warning("Input blocked by safety: %s", input_check.flags)
        return _json_response({
            "response": (
                "I noticed some concerning language. If you're in crisis, "
                "please reach out to the 988 Suicide & Crisis Lifeline by calling or texting 988."
            ),
            "model": "safety-block",
            "safety_flags_in": input_check.flags,
            "safety_flags_out": [],
            "blocked": True,
        })

    safe_input = input_check.filtered_text

    # --- LLM generation ---
    try:
        provider = get_llm_provider()
        llm_result = provider.generate(
            safe_input,
            conversation_history=conversation_history,
        )
    except Exception as exc:
        logger.exception("LLM generation failed")
        return _error_response(f"LLM error: {exc}", status=500)

    # --- Output safety ---
    output_check = check_output_safety(llm_result.text)
    if not output_check.is_safe:
        logger.warning("LLM output blocked by safety: %s", output_check.flags)
        return _json_response({
            "response": (
                "I want to make sure I provide safe and helpful information. "
                "Could you rephrase your question so I can better assist you?"
            ),
            "model": llm_result.model,
            "safety_flags_in": input_check.flags,
            "safety_flags_out": output_check.flags,
            "blocked": True,
        })

    # Persist turn to Firestore if session exists
    if session_id:
        try:
            db = _get_db()
            session_ref = db.collection("sessions").document(session_id)
            session_ref.update({
                "turns": firestore.ArrayUnion([
                    {"role": "user", "content": safe_input, "ts": time.time()},
                    {"role": "assistant", "content": output_check.filtered_text, "ts": time.time()},
                ]),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as exc:
            logger.warning("Failed to persist turn to session %s: %s", session_id, exc)

    return _json_response({
        "response": output_check.filtered_text,
        "model": llm_result.model,
        "safety_flags_in": input_check.flags,
        "safety_flags_out": output_check.flags,
        "is_stub": llm_result.is_stub,
        "usage": {
            "prompt_tokens": llm_result.usage_prompt_tokens,
            "completion_tokens": llm_result.usage_completion_tokens,
        },
    })


@https_fn.on_request(cors=CORS_OPTIONS)
def synthesize_speech(request: https_fn.Request) -> https_fn.Response:
    """Convert text to speech audio.

    Expects JSON body::

        {
            "text": "text to synthesize",
            "voice": "en-US-Neural2-F",   // optional
            "language": "en-US"            // optional
        }

    Returns::

        {
            "audio_base64": "...",
            "audio_format": "mp3",
            "audio_url": null,
            "is_stub": false
        }
    """
    if request.method == "OPTIONS":
        return _json_response({})

    body = _parse_json_body(request)
    if body is None:
        return _error_response("Invalid JSON body")

    text: str | None = body.get("text")
    if not text or not text.strip():
        return _error_response("Missing or empty 'text' field")

    voice: str | None = body.get("voice")
    language = str(body.get("language", "en-US"))

    try:
        provider = get_tts_provider()
        result = provider.synthesize(text, voice=voice, language=language)

        logger.info("TTS result (stub=%s), %d bytes", result.is_stub, len(result.audio_bytes))
        return _json_response({
            "audio_base64": base64.b64encode(result.audio_bytes).decode() if result.audio_bytes else "",
            "audio_format": result.audio_format,
            "sample_rate": result.sample_rate,
            "audio_url": result.audio_url,
            "is_stub": result.is_stub,
        })
    except Exception as exc:
        logger.exception("synthesize_speech failed")
        return _error_response(f"TTS processing error: {exc}", status=500)


@https_fn.on_request(cors=CORS_OPTIONS)
def create_session(request: https_fn.Request) -> https_fn.Response:
    """Create a new voice session in Firestore.

    Expects JSON body::

        {
            "user_id": "optional-user-id",
            "metadata": {}                  // optional
        }

    Returns::

        {
            "session_id": "...",
            "created_at": "..."
        }
    """
    if request.method == "OPTIONS":
        return _json_response({})

    body = _parse_json_body(request) or {}
    user_id: str = body.get("user_id", "anonymous")
    metadata: dict[str, Any] = body.get("metadata", {})
    now = datetime.now(timezone.utc)

    try:
        db = _get_db()
        doc_ref = db.collection("sessions").document()
        session_data = {
            "session_id": doc_ref.id,
            "user_id": user_id,
            "status": "active",
            "turns": [],
            "metadata": metadata,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "ended_at": None,
            "duration_seconds": None,
        }
        doc_ref.set(session_data)

        logger.info("Session created: %s", doc_ref.id)
        return _json_response({"session_id": doc_ref.id, "created_at": now.isoformat()}, status=201)
    except Exception as exc:
        logger.exception("create_session failed")
        return _error_response(f"Firestore error: {exc}", status=500)


@https_fn.on_request(cors=CORS_OPTIONS)
def end_session(request: https_fn.Request) -> https_fn.Response:
    """End a session and compute its duration.

    Expects JSON body::

        {
            "session_id": "..."
        }

    Returns::

        {
            "session_id": "...",
            "duration_seconds": 123.4,
            "turn_count": 5
        }
    """
    if request.method == "OPTIONS":
        return _json_response({})

    body = _parse_json_body(request)
    if body is None:
        return _error_response("Invalid JSON body")

    session_id: str | None = body.get("session_id")
    if not session_id:
        return _error_response("Missing 'session_id' field")

    now = datetime.now(timezone.utc)

    try:
        db = _get_db()
        session_ref = db.collection("sessions").document(session_id)
        doc = session_ref.get()

        if not doc.exists:
            return _error_response(f"Session {session_id} not found", status=404)

        data = doc.to_dict()
        created_str = data.get("created_at", now.isoformat())
        created_at = datetime.fromisoformat(created_str)
        duration = (now - created_at).total_seconds()
        turn_count = len(data.get("turns", []))

        session_ref.update({
            "status": "ended",
            "ended_at": now.isoformat(),
            "duration_seconds": round(duration, 2),
            "updated_at": now.isoformat(),
        })

        logger.info("Session ended: %s (%.1fs, %d turns)", session_id, duration, turn_count)
        return _json_response({
            "session_id": session_id,
            "duration_seconds": round(duration, 2),
            "turn_count": turn_count,
        })
    except Exception as exc:
        logger.exception("end_session failed")
        return _error_response(f"Firestore error: {exc}", status=500)


@https_fn.on_request(cors=CORS_OPTIONS)
def get_metrics(request: https_fn.Request) -> https_fn.Response:
    """Aggregate session metrics from Firestore.

    Accepts optional query params:
        ?status=ended&limit=100

    Returns::

        {
            "total_sessions": 42,
            "active_sessions": 3,
            "ended_sessions": 39,
            "avg_duration_seconds": 87.3,
            "avg_turns_per_session": 4.2,
            "total_turns": 176
        }
    """
    if request.method == "OPTIONS":
        return _json_response({})

    try:
        db = _get_db()
        sessions_ref = db.collection("sessions")

        limit = int(request.args.get("limit", 500))
        docs = sessions_ref.limit(limit).stream()

        total = 0
        active = 0
        ended = 0
        total_duration = 0.0
        total_turns = 0

        for doc in docs:
            data = doc.to_dict()
            total += 1
            status = data.get("status", "unknown")
            if status == "active":
                active += 1
            elif status == "ended":
                ended += 1
                total_duration += data.get("duration_seconds", 0) or 0

            total_turns += len(data.get("turns", []))

        avg_duration = round(total_duration / ended, 2) if ended else 0
        avg_turns = round(total_turns / total, 2) if total else 0

        return _json_response({
            "total_sessions": total,
            "active_sessions": active,
            "ended_sessions": ended,
            "avg_duration_seconds": avg_duration,
            "avg_turns_per_session": avg_turns,
            "total_turns": total_turns,
        })
    except Exception as exc:
        logger.exception("get_metrics failed")
        return _error_response(f"Metrics aggregation error: {exc}", status=500)
