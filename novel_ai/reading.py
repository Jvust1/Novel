from __future__ import annotations

import io

SUPPORTED_EXTENSIONS = (".txt", ".md", ".docx", ".pdf")


def extract_reference_text(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded reference file.

    TXT/MD are decoded as UTF-8; DOCX and PDF are parsed with optional
    dependencies (python-docx / pypdf) that are imported lazily so the core
    pipeline works without them.
    """
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
    raise ValueError(f"暂不支持的参考文本格式: {filename or '(未命名)'}；支持 TXT / MD / DOCX / PDF")
