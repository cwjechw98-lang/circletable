from __future__ import annotations

from pathlib import Path


SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}


def parse_file(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Неподдерживаемый формат файла: {suffix}")

    if suffix == ".pdf":
        return _parse_pdf(path)

    return _parse_text(path)


def _parse_pdf(path: Path) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("Для PDF нужен PyMuPDF (fitz)") from exc

    pages: list[str] = []
    with fitz.open(path) as document:
        for page in document:
            text = page.get_text("text").strip()
            if text:
                pages.append(text)
    return "\n\n".join(pages).strip()


def _parse_text(path: Path) -> str:
    raw = path.read_bytes()
    encoding = _detect_encoding(raw)
    text = raw.decode(encoding, errors="replace")
    return text.replace("\x00", "").strip()


def _detect_encoding(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251", "cp866"):
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin-1"
