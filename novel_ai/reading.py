from __future__ import annotations

import importlib.util
import io
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .text_decoding import decode_reference_text

SUPPORTED_EXTENSIONS = (".txt", ".md", ".docx", ".pdf", ".html", ".htm", ".rtf", ".epub")


def _advanced_extract(filename: str, data: bytes) -> tuple[str, str] | None:
    """Try Docling first, then MarkItDown.

    Both adapters operate on a temporary local file and are optional. Failure
    falls through to the deterministic lightweight readers.
    """
    suffix = Path(filename or "reference.txt").suffix.lower() or ".txt"
    with tempfile.TemporaryDirectory(prefix="novel-reference-") as td:
        path = Path(td) / ("reference" + suffix)
        path.write_bytes(data)

        if importlib.util.find_spec("docling") is not None:
            try:
                from docling.document_converter import DocumentConverter
                result = DocumentConverter().convert(path)
                text = result.document.export_to_markdown()
                if text and text.strip():
                    return text.strip(), "docling"
            except Exception:
                pass

        if importlib.util.find_spec("markitdown") is not None:
            try:
                from markitdown import MarkItDown
                result = MarkItDown().convert(str(path))
                text = getattr(result, "markdown", None) or getattr(result, "text_content", "")
                if text and text.strip():
                    return text.strip(), "markitdown"
            except Exception:
                pass
    return None


def _extract_reference_text_with_backend(filename: str, data: bytes) -> tuple[str, str]:
    """Extract reference text and report the backend actually used."""
    name = (filename or "").lower()
    # Complex formats prefer high-fidelity optional readers when installed.
    if name.endswith((".pdf", ".docx", ".html", ".htm", ".rtf", ".epub")):
        advanced = _advanced_extract(filename, data)
        if advanced is not None:
            return advanced

    if name.endswith(".docx"):
        try:
            from docx import Document
        except ImportError as exc:
            raise ValueError("读取 DOCX 需要 python-docx，或安装 requirements-extras/reference.txt") from exc
        paragraphs = [p.text for p in Document(io.BytesIO(data)).paragraphs]
        text = "\n".join(paragraphs)
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        return text.strip(), "python-docx"

    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("读取 PDF 需要 pypdf，或安装 requirements-extras/reference.txt") from exc
        pages = [page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages]
        return "\n\n".join(part.strip() for part in pages if part.strip()), "pypdf"

    if name.endswith((".html", ".htm", ".rtf", ".epub")):
        raise ValueError(
            f"读取 {Path(filename).suffix} 需要 Docling 或 MarkItDown："
            "pip install -r requirements-extras/reference.txt"
        )

    raise ValueError(
        f"暂不支持的参考文本格式: {filename or '(未命名)'}；"
        "支持 TXT / MD / DOCX / PDF / HTML / RTF / EPUB"
    )


@dataclass(frozen=True)
class ReferenceExtraction:
    text: str
    backend: str
    decoding: dict | None = None


def extract_reference(filename: str, data: bytes, *, encoding: str | None = None) -> ReferenceExtraction:
    if (filename or "").lower().endswith((".txt", ".md")):
        decoded = decode_reference_text(data, encoding=encoding)
        backend = "utf8" if decoded.encoding == "utf-8" and not decoded.had_bom else "text:" + decoded.encoding
        return ReferenceExtraction(decoded.text, backend, decoded.report())
    if encoding is not None:
        raise ValueError("显式文本编码仅适用于 TXT/MD 文件")
    text, backend = _extract_reference_text_with_backend(filename, data)
    return ReferenceExtraction(text, backend)


def extract_reference_text_with_backend(filename: str, data: bytes, *, encoding: str | None = None) -> tuple[str, str]:
    result = extract_reference(filename, data, encoding=encoding)
    return result.text, result.backend


def extract_reference_text(filename: str, data: bytes, *, encoding: str | None = None) -> str:
    return extract_reference(filename, data, encoding=encoding).text
