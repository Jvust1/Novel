from __future__ import annotations

import io
from pathlib import Path
import tempfile
from typing import Literal

SUPPORTED_EXTENSIONS = (".txt", ".md", ".docx", ".pdf")
READER_BACKENDS = ("builtin", "markitdown", "docling")
ReaderBackend = Literal["builtin", "markitdown", "docling"]


def _extract_markitdown(filename: str, data: bytes) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as exc:  # pragma: no cover - depends on env
        raise ValueError(
            "MarkItDown reader 未安装：pip install -r requirements-extras/reference.txt"
        ) from exc

    with tempfile.TemporaryDirectory(prefix="novel-markitdown-") as tmp:
        source = Path(tmp) / (Path(filename).name or "reference.bin")
        source.write_bytes(data)
        try:
            result = MarkItDown().convert(str(source))
        except Exception as exc:  # pragma: no cover - backend-specific failures
            raise ValueError(f"MarkItDown 读取失败: {exc}") from exc
    text = getattr(result, "text_content", None)
    if not isinstance(text, str) or not text.strip():
        raise ValueError("MarkItDown 未返回可用文本")
    return text.strip()


def _extract_docling(filename: str, data: bytes) -> str:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:  # pragma: no cover - depends on env
        raise ValueError(
            "Docling reader 未安装：pip install -r requirements-extras/reference.txt"
        ) from exc

    with tempfile.TemporaryDirectory(prefix="novel-docling-") as tmp:
        source = Path(tmp) / (Path(filename).name or "reference.bin")
        source.write_bytes(data)
        try:
            result = DocumentConverter().convert(str(source))
            text = result.document.export_to_markdown()
        except Exception as exc:  # pragma: no cover - backend-specific failures
            raise ValueError(f"Docling 读取失败: {exc}") from exc
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Docling 未返回可用文本")
    return text.strip()


def extract_with_backend(
    filename: str,
    data: bytes,
    *,
    backend: ReaderBackend,
) -> str:
    """Read a document with one explicitly selected backend."""
    if backend == "markitdown":
        return _extract_markitdown(filename, data)
    if backend == "docling":
        return _extract_docling(filename, data)
    if backend == "builtin":
        return _extract_builtin(filename, data)
    raise ValueError(f"未知 reader backend: {backend}; 可选值: {', '.join(READER_BACKENDS)}")


def _extract_builtin(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith((".txt", ".md")):
        return data.decode("utf-8", errors="ignore")
    if name.endswith(".docx"):
        try:
            from docx import Document
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ValueError("读取 DOCX 需要 python-docx：pip install python-docx") from exc
        paragraphs = [p.text for p in Document(io.BytesIO(data)).paragraphs]
        text = "\n".join(paragraphs)
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        return text.strip()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - depends on env
            raise ValueError("读取 PDF 需要 pypdf：pip install pypdf") from exc
        pages = [page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages]
        return "\n\n".join(part.strip() for part in pages if part.strip())
    raise ValueError(
        f"暂不支持的参考文本格式: {filename or '(未命名)'}；支持 TXT / MD / DOCX / PDF"
    )


def extract_reference_text(
    filename: str,
    data: bytes,
    *,
    backend: ReaderBackend = "builtin",
) -> str:
    """Extract reference text with a selected reader backend.

    The built-in reader remains the default and is dependency-light. Docling
    and MarkItDown are explicit optional backends so installing them cannot
    silently change frozen benchmark parsing.
    """
    return extract_with_backend(filename, data, backend=backend)
