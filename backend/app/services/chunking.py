"""Нарезка документа на фрагменты для поиска.

Фрагменты собираются из целых абзацев до 800 символов. Новый раздел начинает новый фрагмент,
если текущий уже набрал 400 символов, — мелкие разделы склеиваются с соседними. Короткий
последний абзац повторяется в начале следующего фрагмента, чтобы не терять связь на стыке.
"""

import re
from dataclasses import dataclass

from app.services.extract import Unit

MAX_CHARS = 800
FLUSH_AT_HEADING = 400
OVERLAP_MAX = 150


@dataclass
class Draft:
    # Раздел, к которому относится начало фрагмента
    heading: str | None
    text: str


def split_long(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Абзац длиннее лимита делится по предложениям (а предложение-гигант — по словам)."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?…])\s+", text):
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            parts.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > limit:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


def make_chunks(units: list[Unit]) -> list[Draft]:
    drafts: list[Draft] = []
    heading: str | None = None
    start_heading: str | None = None
    buf: list[str] = []

    def size() -> int:
        return sum(len(x) + 1 for x in buf)

    def flush() -> None:
        if buf:
            drafts.append(Draft(start_heading, "\n".join(buf)))
        buf.clear()

    for kind, text in units:
        if kind == "h":
            if size() >= FLUSH_AT_HEADING:
                flush()
            heading = text
            if not buf:
                start_heading = text
            buf.append(text)
            continue
        for piece in split_long(text):
            if buf and size() + len(piece) > MAX_CHARS:
                last = buf[-1]
                flush()
                start_heading = heading
                if (
                    len(last) <= OVERLAP_MAX
                    and last != heading
                    and len(last) + len(piece) < MAX_CHARS
                ):
                    buf.append(last)
            if not buf:
                start_heading = heading
            buf.append(piece)
    flush()
    # Заголовок в самом конце документа без текста под ним — не фрагмент
    return [d for d in drafts if d.text.strip() != (d.heading or "").strip()]


def embedding_input(title: str, draft: Draft) -> str:
    """Текст для эмбеддинга: название документа и раздел дают контекст строкам прайса и таблиц."""
    head = [title]
    if draft.heading and not draft.text.startswith(draft.heading):
        head.append(draft.heading)
    return "\n".join([*head, draft.text])
