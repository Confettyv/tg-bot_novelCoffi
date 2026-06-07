from __future__ import annotations

import json
import re
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.config import Settings


@dataclass(slots=True)
class TranslationResult:
    translated_text: str
    context_summary: str
    quality_notes: str = ""


class LLMConfigurationError(RuntimeError):
    pass


class LLMClient:
    GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.openai_client: AsyncOpenAI | None = None
        self.gemini_client: AsyncOpenAI | None = None

        if settings.openai_api_key:
            self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

        if settings.gemini_api_key:
            self.gemini_client = AsyncOpenAI(
                api_key=settings.gemini_api_key,
                base_url=self.GEMINI_OPENAI_BASE_URL,
            )

    async def translate_json(self, messages: list[dict[str, str]], provider: str | None = None) -> TranslationResult:
        provider = self._normalize_provider(provider or self.settings.llm_provider)

        if provider == "openai":
            raw = await self._call_openai(messages)
        elif provider == "gemini":
            raw = await self._call_gemini(messages)
        else:
            raise LLMConfigurationError(
                "Неизвестный LLM_PROVIDER. Используй openai или gemini. "
                "В Telegram можно переключить командой /provider openai или /provider gemini."
            )

        data = self._parse_json(raw)

        return TranslationResult(
            translated_text=str(data.get("translated_text") or raw).strip(),
            context_summary=str(data.get("context_summary") or "").strip(),
            quality_notes=str(data.get("quality_notes") or "").strip(),
        )

    async def _call_openai(self, messages: list[dict[str, str]]) -> str:
        if self.openai_client is None:
            raise LLMConfigurationError(
                "Для провайдера OpenAI нужен OPENAI_API_KEY в .env. "
                "Или переключись на Gemini: /provider gemini. "
                "Для полностью бесплатного режима используй /mode free."
            )

        response = await self.openai_client.responses.create(
            model=self.settings.openai_model,
            input=messages,
        )
        return (response.output_text or "").strip()

    async def _call_gemini(self, messages: list[dict[str, str]]) -> str:
        if self.gemini_client is None:
            raise LLMConfigurationError(
                "Для провайдера Gemini нужен GEMINI_API_KEY в .env. "
                "Или переключись на OpenAI: /provider openai. "
                "Для полностью бесплатного режима используй /mode free."
            )

        response = await self.gemini_client.chat.completions.create(
            model=self.settings.gemini_model,
            messages=messages,
            temperature=0.2,
        )
        message = response.choices[0].message
        content = message.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if text:
                        parts.append(str(text))
                else:
                    text = getattr(part, "text", None) or getattr(part, "content", None)
                    if text:
                        parts.append(str(text))
            return "".join(parts).strip()
        return str(content or "").strip()

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        value = (provider or "").strip().lower()
        if value in {"openai", "gemini"}:
            return value
        return "openai"

    @staticmethod
    def _parse_json(raw: str) -> dict[str, object]:
        if not raw:
            return {}
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            # Defensive fallback for occasional fenced or prefixed JSON.
            match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
            if not match:
                return {}
            try:
                value = json.loads(match.group(0))
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}
