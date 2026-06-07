from __future__ import annotations

STYLE_DESCRIPTIONS = {
    "literal": "точный перевод с минимальной адаптацией, без художественных вольностей",
    "neutral": "естественный русский перевод без выраженной стилизации",
    "literary": "литературный перевод: живой русский язык, сохранение смысла, эмоций и сцены",
    "ranobe": "стиль ранобэ/веб-новеллы: динамичные диалоги, естественная адаптация обращений, без канцелярита",
}

LANGUAGE_NAMES = {
    "auto": "автоматическое определение",
    "en": "английский",
    "ja": "японский",
    "ko": "корейский",
}


def glossary_to_text(glossary: list[dict[str, str]]) -> str:
    if not glossary:
        return "Глоссарий пуст. Если встречаются имена, термины, титулы и устойчивые обращения, сохраняй их последовательно."

    lines = []
    for item in glossary:
        note = f" — {item['note']}" if item.get("note") else ""
        lines.append(f"- {item['source_term']} => {item['target_term']}{note}")
    return "\n".join(lines)


def build_translation_prompt(
    *,
    source_language: str,
    target_language: str,
    style_mode: str,
    glossary_text: str,
    previous_context: str,
    chunk_index: int,
    chunks_total: int,
    source_text: str,
) -> list[dict[str, str]]:
    style_description = STYLE_DESCRIPTIONS.get(style_mode, STYLE_DESCRIPTIONS["literary"])
    language_name = LANGUAGE_NAMES.get(source_language, source_language)

    system = """
Ты профессиональный литературный переводчик азиатских и англоязычных веб-новелл на русский язык.
Твоя задача — переводить не сухо и не машинно, а естественным русским литературным языком.

Критически важные правила:
1. Не добавляй события, мысли, описания или реплики, которых нет в оригинале.
2. Не сокращай сцену и не пересказывай вместо перевода.
3. Сохраняй последовательность действий, причинно-следственную связь и эмоциональный тон.
4. Имена, титулы, обращения и термины мира используй последовательно.
5. Диалоги должны звучать живо по-русски, но без потери смысла.
6. Если пол персонажа неясен, избегай необоснованных местоимений, пока контекст не прояснит ситуацию.
7. Не используй канцелярит и тяжёлые академические обороты.
8. Не вставляй комментарии переводчика.

Верни строго JSON без markdown:
{
  "translated_text": "готовый перевод фрагмента на русский",
  "context_summary": "обновлённое краткое резюме событий, персонажей, отношений и терминов для следующих фрагментов",
  "quality_notes": "короткие технические заметки: неоднозначные имена, обращения, пол персонажа, термины"
}
""".strip()

    user = f"""
Исходный язык: {language_name}
Целевой язык: {target_language}
Стиль: {style_description}
Фрагмент: {chunk_index + 1} из {chunks_total}

Контекст предыдущих фрагментов/глав:
{previous_context or "Контекста пока нет."}

Глоссарий:
{glossary_text}

Текст для перевода:
<<<SOURCE_TEXT
{source_text}
SOURCE_TEXT
""".strip()

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_hybrid_editor_prompt(
    *,
    source_language: str,
    target_language: str,
    style_mode: str,
    glossary_text: str,
    previous_context: str,
    chunk_index: int,
    chunks_total: int,
    source_text: str,
    draft_translation: str,
) -> list[dict[str, str]]:
    style_description = STYLE_DESCRIPTIONS.get(style_mode, STYLE_DESCRIPTIONS["literary"])
    language_name = LANGUAGE_NAMES.get(source_language, source_language)

    system = """
Ты литературный редактор перевода веб-новелл на русский язык.
У тебя есть оригинальный фрагмент и машинный черновой перевод.
Твоя задача — исправить черновик: сделать русский текст живым, логичным и литературным, но не выдумывать новые события.

Правила:
1. Основной смысл сверяй с оригиналом, а не только с черновиком.
2. Не добавляй события, эмоции, описания или реплики, которых нет в оригинале.
3. Не сокращай сцену.
4. Исправляй машинные конструкции, кривые падежи, неестественный порядок слов и сухие фразы.
5. Имена, титулы, обращения и термины применяй по глоссарию.
6. Диалоги должны звучать естественно по-русски.
7. Сохраняй стиль, тон сцены и причинно-следственную связь.
8. Не вставляй комментарии переводчика.

Верни строго JSON без markdown:
{
  "translated_text": "отредактированный русский перевод фрагмента",
  "context_summary": "обновлённое краткое резюме событий, персонажей, отношений и терминов для следующих фрагментов",
  "quality_notes": "короткие технические заметки по спорным местам"
}
""".strip()

    user = f"""
Исходный язык: {language_name}
Целевой язык: {target_language}
Стиль: {style_description}
Фрагмент: {chunk_index + 1} из {chunks_total}

Контекст предыдущих фрагментов/глав:
{previous_context or "Контекста пока нет."}

Глоссарий:
{glossary_text}

Оригинальный текст:
<<<SOURCE_TEXT
{source_text}
SOURCE_TEXT

Машинный черновик LibreTranslate:
<<<DRAFT_TRANSLATION
{draft_translation}
DRAFT_TRANSLATION
""".strip()

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
