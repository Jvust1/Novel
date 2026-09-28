import io
import sys
from types import ModuleType, SimpleNamespace

import pytest

from novel_ai.reading import extract_reference_text


def test_txt_is_decoded_directly():
    data = "他推开门。屋里没人。".encode("utf-8")
    assert extract_reference_text("ref.txt", data) == "他推开门。屋里没人。"


def test_docx_paragraphs_are_preserved():
    from docx import Document

    doc = Document()
    doc.add_paragraph("第一段：夜班电台。")
    doc.add_paragraph("")
    doc.add_paragraph("第二段：23:17，电话准时打入。")
    buf = io.BytesIO()
    doc.save(buf)
    text = extract_reference_text("ref.docx", buf.getvalue())
    assert text.startswith("第一段：夜班电台。")
    assert "第二段：23:17，电话准时打入。" in text
    assert "\n\n\n" not in text


def make_pdf(text: str) -> bytes:
    """Hand-build a minimal valid single-page PDF so tests need no PDF writer."""
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF"
    ).encode()
    return bytes(out)


def test_pdf_text_is_extracted():
    text = extract_reference_text("ref.pdf", make_pdf("Hello PDF extraction"))
    assert "Hello PDF extraction" in text


def test_unsupported_extension_raises_clear_error():
    with pytest.raises(ValueError, match="DOCX"):
        extract_reference_text("ref.epub", b"whatever")


def test_corrupt_pdf_raises_pdf_error_not_silent_empty():
    from pypdf.errors import PdfReadError

    with pytest.raises((PdfReadError, ValueError)):
        extract_reference_text("bad.pdf", b"not a pdf at all")


def test_markitdown_backend_is_explicit_and_uses_temp_input(monkeypatch):
    class FakeMarkItDown:
        def convert(self, path):
            assert path.endswith("ref.txt")
            return SimpleNamespace(text_content="MarkItDown output")

    monkeypatch.setitem(
        sys.modules,
        "markitdown",
        SimpleNamespace(MarkItDown=FakeMarkItDown),
    )
    assert extract_reference_text("ref.txt", b"ignored", backend="markitdown") == "MarkItDown output"


def test_docling_backend_is_explicit(monkeypatch):
    converter_module = ModuleType("docling.document_converter")

    class FakeDocumentConverter:
        def convert(self, path):
            assert path.endswith("ref.txt")
            return SimpleNamespace(document=SimpleNamespace(export_to_markdown=lambda: "Docling output"))

    converter_module.DocumentConverter = FakeDocumentConverter
    package = ModuleType("docling")
    package.document_converter = converter_module
    monkeypatch.setitem(sys.modules, "docling", package)
    monkeypatch.setitem(sys.modules, "docling.document_converter", converter_module)

    assert extract_reference_text("ref.txt", b"ignored", backend="docling") == "Docling output"


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError, match="未知 reader backend"):
        extract_reference_text("ref.txt", b"ignored", backend="unknown")
