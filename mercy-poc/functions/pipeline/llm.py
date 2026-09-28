"""LLM provider abstraction for Mercy voice assistant.

Supports Vertex AI (Gemini) and OpenAI, with automatic fallback to stub mode
when credentials are unavailable.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MERCY_SYSTEM_PROMPT = """\
You are Mercy, a compassionate and knowledgeable healthcare voice assistant.

Guidelines:
- Speak in a warm, empathetic tone appropriate for patients and caregivers.
- Help users understand their care plans, medications, and appointments.
- NEVER diagnose conditions or prescribe treatments.
- Always recommend consulting a qualified healthcare professional for medical decisions.
- If a user expresses distress or mentions self-harm, respond with empathy and \
provide crisis-resource information (e.g., 988 Suicide & Crisis Lifeline).
- Keep responses concise and suitable for spoken delivery (1-3 sentences when possible).
- Respect patient privacy — never ask for or repeat sensitive personal information.
"""


@dataclass
class LLMResponse:
    """Result returned by an LLM provider."""

    text: str
    model: str
    usage_prompt_tokens: int = 0
    usage_completion_tokens: int = 0
    is_stub: bool = False


class LLMProvider(ABC):
    """Abstract interface for LLM providers."""

    @abstractmethod
    def generate(
        self,
        user_message: str,
        *,
        conversation_history: list[dict[str, str]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
    ) -> LLMResponse:
        """Generate a response to the user message.

        Args:
            user_message: Current user turn.
            conversation_history: Prior turns as ``[{"role": ..., "content": ...}]``.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in the completion.

        Returns:
            LLMResponse with the generated text.
        """


class VertexAILLM(LLMProvider):
    """Google Vertex AI (Gemini) implementation.

    Falls back to a stub response when credentials or project config are missing.
    """

    def __init__(self) -> None:
        self._model = None
        self._project = os.getenv("GOOGLE_CLOUD_PROJECT")
        self._location = os.getenv("VERTEX_AI_LOCATION", "us-central1")

        try:
            import vertexai  # type: ignore[import-untyped]
            from vertexai.generative_models import GenerativeModel  # type: ignore[import-untyped]

            vertexai.init(project=self._project, location=self._location)
            self._model = GenerativeModel("gemini-1.5-flash", system_instruction=MERCY_SYSTEM_PROMPT)
            logger.info("VertexAILLM initialised (project=%s, location=%s).", self._project, self._location)
        except Exception:
            logger.warning("Vertex AI credentials unavailable — running in stub mode.")

    def generate(
        self,
        user_message: str,
        *,
        conversation_history: list[dict[str, str]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
    ) -> LLMResponse:
        if self._model is None:
            return self._stub_generate(user_message)

        try:
            from vertexai.generative_models import GenerationConfig  # type: ignore[import-untyped]

            config = GenerationConfig(temperature=temperature, max_output_tokens=max_tokens)
            prompt_parts: list[str] = []
            if conversation_history:
                for turn in conversation_history:
                    prompt_parts.append(f"{turn['role']}: {turn['content']}")
            prompt_parts.append(f"user: {user_message}")
            full_prompt = "\n".join(prompt_parts)

            response = self._model.generate_content(full_prompt, generation_config=config)
            return LLMResponse(
                text=response.text,
                model="gemini-1.5-flash",
                usage_prompt_tokens=getattr(response.usage_metadata, "prompt_token_count", 0),
                usage_completion_tokens=getattr(response.usage_metadata, "candidates_token_count", 0),
            )
        except Exception as exc:
            logger.error("VertexAILLM generation failed: %s", exc)
            return self._stub_generate(user_message)

    @staticmethod
    def _stub_generate(user_message: str) -> LLMResponse:
        logger.info("VertexAILLM returning stub response.")
        return LLMResponse(
            text=(
                "I understand you'd like help with your healthcare needs. "
                "I'm currently in demo mode, but once fully connected I can help you "
                "understand your care plan, medications, and appointments. "
                "Please consult your healthcare provider for specific medical advice."
            ),
            model="vertex-stub",
            is_stub=True,
        )


class OpenAILLM(LLMProvider):
    """OpenAI ChatCompletion implementation.

    Falls back to a stub response when the API key is missing.
    """

    def __init__(self) -> None:
        self._client = None
        self._api_key = os.getenv("OPENAI_API_KEY")

        if self._api_key:
            try:
                from openai import OpenAI  # type: ignore[import-untyped]
                self._client = OpenAI(api_key=self._api_key)
                logger.info("OpenAILLM initialised.")
            except Exception:
                logger.warning("OpenAI client init failed — running in stub mode.")
        else:
            logger.warning("OPENAI_API_KEY not set — running in stub mode.")

    def generate(
        self,
        user_message: str,
        *,
        conversation_history: list[dict[str, str]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
    ) -> LLMResponse:
        if self._client is None:
            return self._stub_generate(user_message)

        try:
            messages: list[dict[str, str]] = [{"role": "system", "content": MERCY_SYSTEM_PROMPT}]
            if conversation_history:
                messages.extend(conversation_history)
            messages.append({"role": "user", "content": user_message})

            response = self._client.chat.completions.create(
                model="gpt-4o",
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = response.choices[0]
            return LLMResponse(
                text=choice.message.content or "",
                model=response.model,
                usage_prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                usage_completion_tokens=response.usage.completion_tokens if response.usage else 0,
            )
        except Exception as exc:
            logger.error("OpenAILLM generation failed: %s", exc)
            return self._stub_generate(user_message)

    @staticmethod
    def _stub_generate(user_message: str) -> LLMResponse:
        logger.info("OpenAILLM returning stub response.")
        return LLMResponse(
            text=(
                "I understand you'd like help with your healthcare needs. "
                "I'm currently in demo mode, but once fully connected I can help you "
                "understand your care plan, medications, and appointments. "
                "Please consult your healthcare provider for specific medical advice."
            ),
            model="openai-stub",
            is_stub=True,
        )


def get_llm_provider(provider: str | None = None) -> LLMProvider:
    """Factory: return the configured LLM provider.

    Args:
        provider: Explicit provider name ('vertex', 'openai').
                  Defaults to the ``LLM_PROVIDER`` env var, then ``'vertex'``.

    Returns:
        An initialised LLMProvider instance.
    """
    name = (provider or os.getenv("LLM_PROVIDER", "vertex")).lower()
    if name == "openai":
        return OpenAILLM()
    return VertexAILLM()
