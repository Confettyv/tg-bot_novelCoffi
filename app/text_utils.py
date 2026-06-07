from __future__ import annotations

import re
import unicodedata
from pathlib import Path


JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
KOREAN_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")


def normalize_text(text: str) -> str:
    """Normalize whitespace without destroying paragraph structure."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def detect_language(text: str) -> str:
    sample = text[:5000]
    if KOREAN_RE.search(sample):
        return "ko"
    # Japanese may contain kanji also used by Chinese, but the MVP supports JA/KO/EN.
    if JAPANESE_RE.search(sample):
        return "ja"
    return "en"


def safe_filename(name: str, max_len: int = 90) -> str:
    base = Path(name).stem or "chapter"
    base = re.sub(r"[^\w\-.а-яА-ЯёЁ一-龯ぁ-んァ-ン가-힣 ]+", "_", base, flags=re.UNICODE)
    base = re.sub(r"\s+", "_", base).strip("._")
    return (base[:max_len] or "chapter") + ".txt"


def read_text_safely(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
        try:
            return normalize_text(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    return normalize_text(raw.decode("utf-8", errors="replace"))


def split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]

    # Prefer splitting after sentence punctuation. Handles Russian/English/JP/KO punctuation.
    sentences = re.split(r"(?<=[.!?。！？…])\s+", paragraph)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if not sentence:
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                chunks.append(current)
            if len(sentence) <= max_chars:
                current = sentence
            else:
                # Last-resort hard split for extremely long unbroken paragraphs.
                for i in range(0, len(sentence), max_chars):
                    part = sentence[i : i + max_chars]
                    if len(part) == max_chars:
                        chunks.append(part)
                    else:
                        current = part
    if current:
        chunks.append(current)
    return chunks


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split a chapter by paragraphs while preserving coherent blocks as much as possible."""
    text = normalize_text(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    result: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        parts = split_long_paragraph(paragraph, max_chars)
        for part in parts:
            add_len = len(part) + 2
            if current and current_len + add_len > max_chars:
                result.append("\n\n".join(current).strip())
                current = [part]
                current_len = len(part)
            else:
                current.append(part)
                current_len += add_len

    if current:
        result.append("\n\n".join(current).strip())

    return result
