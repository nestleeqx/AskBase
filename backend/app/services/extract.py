"""Текст из PDF, DOCX, TXT и HTML — в виде последовательности заголовков и абзацев.

Заголовки нужны нарезке: фрагмент помнит, к какому разделу документа он относится.
"""

import io
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePath

from bs4 import BeautifulSoup

# ("h", "Хирургия") — заголовок раздела, ("p", "4.01 Удаление зуба простое 3 500") — абзац
Unit = tuple[str, str]

HEADING_MAX = 70
KINDS = {".pdf": "pdf", ".docx": "docx", ".txt": "txt", ".md": "txt"}


class ExtractError(Exception):
    """Документ не удалось прочитать. Текст ошибки показывается пользователю как есть."""


@dataclass
class Extracted:
    title: str
    units: list[Unit] = field(default_factory=list)
    pages: int | None = None

    @property
    def chars(self) -> int:
        return sum(len(text) for _, text in self.units)


def clean(line: str) -> str:
    line = line.replace(" ", " ").replace("​", "").replace("­", "")
    return re.sub(r"[ \t\f\v]+", " ", line).strip()


def looks_like_heading(line: str) -> bool:
    """Короткая строка без цифр и без точки в конце, с заглавной буквы — похожа на заголовок."""
    if not line or len(line) > HEADING_MAX or len(line.split()) > 8:
        return False
    if line[-1] in ".:;,!?" or re.search(r"\d", line):
        return False
    return line[0].isupper() or line[0] in '«"'


def kind_of(filename: str) -> str:
    suffix = PurePath(filename).suffix.lower()
    if suffix == ".doc":
        raise ExtractError("Старый формат .doc не поддерживается. Сохраните файл в Word как DOCX.")
    if suffix not in KINDS:
        raise ExtractError("Поддерживаются файлы PDF, DOCX и TXT.")
    return KINDS[suffix]


def extract_file(kind: str, data: bytes, filename: str, max_pages: int) -> Extracted:
    stem = PurePath(filename).stem.replace("_", " ").strip() or "Документ"
    if kind == "pdf":
        return extract_pdf(data, stem, max_pages)
    if kind == "docx":
        return extract_docx(data, stem)
    if kind == "html":
        return extract_html(data, stem)
    return extract_txt(decode_text(data), stem)


# --- PDF ---

_PRICE_TAIL = re.compile(r"(от\s)?\d[\d\s]*(₽|руб\.?)?|бесплатно", re.I)


def _continues(line: str) -> bool:
    """Строка — продолжение предыдущей: PDF переносит длинные строки таблиц и абзацев."""
    return line[0].islower() or line[0] in ")»,.;:—–" or bool(_PRICE_TAIL.fullmatch(line))


def _shape(line: str) -> str:
    """Строка без номеров страниц: «стр. 1 из 3» и «стр. 2 из 3» совпадут. Пусто — не текст."""
    if len(re.findall(r"[^\W\d_]", line)) < 4:
        return ""
    return re.sub(r"\d+", "#", line)


def extract_pdf(data: bytes, stem: str, max_pages: int) -> Extracted:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractError("PDF защищён паролем. Снимите защиту и загрузите файл снова.")
        if len(reader.pages) > max_pages:
            raise ExtractError(f"В PDF больше {max_pages} страниц — для демо это слишком много.")
        pages = [
            [clean(line) for line in (p.extract_text() or "").splitlines()] for p in reader.pages
        ]
        meta_title = clean((reader.metadata or {}).get("/Title") or "")
    except ExtractError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError) as e:
        raise ExtractError("Не удалось прочитать PDF: файл повреждён или это не PDF.") from e

    # Шапки таблиц и колонтитулы повторяются на каждой странице — в поиске они только шумят.
    # Строки из одних цифр (цены, перенесённые на отдельную строку) повторами не считаются
    shape = Counter(_shape(line) for lines in pages for line in lines)
    units: list[Unit] = []
    for lines in pages:
        for line in lines:
            if not line or (_shape(line) and shape[_shape(line)] >= 3):
                continue
            if units and units[-1][0] == "p" and _continues(line):
                units[-1] = ("p", f"{units[-1][1]} {line}")
            else:
                units.append(("h" if looks_like_heading(line) else "p", line))

    if sum(len(t) for _, t in units) < 50:
        raise ExtractError(
            "В PDF не нашлось текста — похоже, это скан. Загрузите PDF с текстом или DOCX."
        )
    title = meta_title or next((t for k, t in units if k == "h"), stem)
    return Extracted(title=title, units=units, pages=len(pages))


# --- DOCX ---


def table_units(rows: list[list[str]]) -> list[Unit]:
    """Строка таблицы с шапкой → «Врач: …; Стаж: …»: так строка понятна и без шапки рядом."""
    rows = [row for row in rows if any(row)]
    if not rows:
        return []
    head, body = rows[0], rows[1:]
    if not body or len(head) < 2:
        return [("p", " | ".join(c for c in row if c)) for row in rows]
    units = []
    for row in body:
        pairs = [f"{h}: {c}" if h else c for h, c in zip(head, row, strict=False) if c]
        units.append(("p", "; ".join(pairs)))
    return units


def _dedupe_cells(cells: list[str]) -> list[str]:
    # Объединённые ячейки python-docx отдаёт повторами одного текста
    out: list[str] = []
    for cell in cells:
        if not out or cell != out[-1]:
            out.append(cell)
    return out


def extract_docx(data: bytes, stem: str) -> Extracted:
    from docx import Document as DocxDocument
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        doc = DocxDocument(io.BytesIO(data))
    except Exception as e:  # python-docx бросает разные ошибки на битом zip/xml
        raise ExtractError("Не удалось прочитать DOCX: файл повреждён или это не DOCX.") from e

    units: list[Unit] = []
    for el in doc.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            par = Paragraph(el, doc)
            text = clean(par.text)
            if not text:
                continue
            style = (par.style.name if par.style is not None else "") or ""
            if style.startswith(("Heading", "Title", "Заголовок", "Название")):
                units.append(("h", text))
            elif style.startswith(("List", "Список")):
                units.append(("p", f"• {text}"))
            else:
                units.append(("p", text))
        elif tag == "tbl":
            table = Table(el, doc)
            rows = [_dedupe_cells([clean(c.text) for c in row.cells]) for row in table.rows]
            units += table_units(rows)

    title = clean(doc.core_properties.title or "") or next((t for k, t in units if k == "h"), stem)
    return Extracted(title=title, units=units)


# --- TXT ---


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ExtractError("Не удалось прочитать текст: сохраните файл в кодировке UTF-8.")


def extract_txt(text: str, stem: str) -> Extracted:
    units: list[Unit] = []
    for para in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = [clean(line) for line in para.splitlines()]
        lines = [line for line in lines if line]
        # Строки капсом в начале абзаца — заголовки разделов
        while lines and lines[0].isupper() and len(lines[0]) <= HEADING_MAX:
            units.append(("h", lines.pop(0)))
        if len(lines) == 1 and looks_like_heading(lines[0]):
            units.append(("h", lines[0]))
        elif lines:
            units.append(("p", "\n".join(lines)))
    return Extracted(title=stem, units=units)


# --- HTML ---

_DROP = [
    "script",
    "style",
    "noscript",
    "svg",
    "nav",
    "header",
    "footer",
    "form",
    "iframe",
    "template",
]
_BLOCKS = ["h1", "h2", "h3", "h4", "p", "li", "table", "pre", "blockquote", "dt", "dd"]


def extract_html(data: bytes | str, fallback_title: str) -> Extracted:
    soup = BeautifulSoup(data, "html.parser")
    page_title = clean(soup.title.get_text()) if soup.title else ""
    for tag in soup(_DROP):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup

    units: list[Unit] = []
    for el in root.find_all(_BLOCKS):
        # Вложенное уже попало в текст родителя: абзац внутри пункта списка, ячейки таблицы
        if el.find_parent(["p", "li", "blockquote", "dd", "table", "pre"]):
            continue
        if el.name == "table":
            rows = [
                _dedupe_cells([clean(c.get_text(" ")) for c in tr.find_all(["th", "td"])])
                for tr in el.find_all("tr")
            ]
            units += table_units(rows)
            continue
        # Пробел между тегами не должен отрывать знак препинания: «<b>24 часа</b>.»
        text = re.sub(r"\s+([.,;:!?»)])", r"\1", clean(el.get_text(" ")))
        if not text:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            units.append(("h", text))
        else:
            units.append(("p", f"• {text}" if el.name == "li" else text))

    # Вёрстка на одних div: блоки собрали меньше половины текста — берём его построчно
    if sum(len(t) for _, t in units) < len(clean(root.get_text(" "))) / 2:
        lines = [clean(line) for line in root.get_text("\n").splitlines()]
        units = [("h" if looks_like_heading(x) else "p", x) for x in lines if x]

    h1 = next((t for k, t in units if k == "h"), "")
    return Extracted(title=h1 or page_title or fallback_title, units=units)
