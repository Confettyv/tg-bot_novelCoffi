from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.db import Project
from app.services.libretranslate import LibreTranslateClient
from app.services.llm import LLMClient
from app.services.prompts import build_hybrid_editor_prompt, build_translation_prompt, glossary_to_text
from app.text_utils import chunk_text, detect_language


ProgressCallback = Callable[[int, int], Awaitable[None]]


@dataclass(slots=True)
class ChapterTranslation:
    translated_text: str
    source_language: str
    context_summary: str
    chunks_total: int
    translation_mode: str
    llm_provider: str


class TranslationService:
    def __init__(self, llm: LLMClient, libretranslate: LibreTranslateClient, chunk_max_chars: int):
        self.llm = llm
        self.libretranslate = libretranslate
        self.chunk_max_chars = chunk_max_chars

    async def translate_chapter(
        self,
        *,
        text: str,
        project: Project,
        glossary: list[dict[str, str]],
        progress: ProgressCallback | None = None,
    ) -> ChapterTranslation:
        source_language = project.source_language
        if source_language == "auto":
            source_language = detect_language(text)

        chunks = chunk_text(text, self.chunk_max_chars)
        if not chunks:
            return ChapterTranslation("", source_language, project.context_summary, 0, project.translation_mode, project.llm_provider)

        mode = project.translation_mode or "hybrid"
        llm_provider = project.llm_provider or "openai"
        glossary_text = glossary_to_text(glossary)
        context_summary = project.context_summary
        translated_chunks: list[str] = []

        for index, chunk in enumerate(chunks):
            if mode == "free":
                translated = await self._translate_free(
                    chunk=chunk,
                    source_language=source_language,
                    target_language=project.target_language,
                    glossary=glossary,
                )
            elif mode == "quality":
                messages = build_translation_prompt(
                    source_language=source_language,
                    target_language=project.target_language,
                    style_mode=project.style_mode,
                    glossary_text=glossary_text,
                    previous_context=context_summary,
                    chunk_index=index,
                    chunks_total=len(chunks),
                    source_text=chunk,
                )
                result = await self.llm.translate_json(messages, provider=llm_provider)
                translated = result.translated_text
                if result.context_summary:
                    context_summary = result.context_summary[:6000]
            elif mode == "hybrid":
                draft = await self._translate_free(
                    chunk=chunk,
                    source_language=source_language,
                    target_language=project.target_language,
                    glossary=glossary,
                )
                messages = build_hybrid_editor_prompt(
                    source_language=source_language,
                    target_language=project.target_language,
                    style_mode=project.style_mode,
                    glossary_text=glossary_text,
                    previous_context=context_summary,
                    chunk_index=index,
                    chunks_total=len(chunks),
                    source_text=chunk,
                    draft_translation=draft,
                )
                result = await self.llm.translate_json(messages, provider=llm_provider)
                translated = result.translated_text
                if result.context_summary:
                    context_summary = result.context_summary[:6000]
            else:
                raise ValueError("Неизвестный режим перевода. Используй /mode free, /mode hybrid или /mode quality.")

            translated_chunks.append(translated)

            if progress is not None:
                await progress(index + 1, len(chunks))

        return ChapterTranslation(
            translated_text="\n\n".join(part.strip() for part in translated_chunks if part.strip()),
            source_language=source_language,
            context_summary=context_summary,
            chunks_total=len(chunks),
            translation_mode=mode,
            llm_provider=llm_provider,
        )

    async def _translate_free(
        self,
        *,
        chunk: str,
        source_language: str,
        target_language: str,
        glossary: list[dict[str, str]],
    ) -> str:
        translated = await self.libretranslate.translate(
            text=chunk,
            source_language=source_language,
            target_language=target_language,
        )
        return self._apply_simple_glossary(translated, glossary)

    @staticmethod
    def _apply_simple_glossary(text: str, glossary: list[dict[str, str]]) -> str:
        # This is intentionally simple. The LLM modes handle glossary semantically;
        # free mode only performs basic replacement when the source term survives in the draft.
        result = text
        for item in glossary:
            source = str(item.get("source_term") or "").strip()
            target = str(item.get("target_term") or "").strip()
            if source and target:
                result = result.replace(source, target)
        return result
