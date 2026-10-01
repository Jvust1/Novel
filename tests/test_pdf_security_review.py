"""Independent PDF compatibility and fail-closed UI checks using synthetic data.

All PDF parsing, including malformed input, runs in a child with CPU, memory,
and wall-clock limits. No reference novels, optional readers, or model calls.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _run_bounded(case: str, tmp_path: Path) -> None:
    pytest.importorskip("resource")
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            filter(None, [os.environ.get("PYTHONPATH"), str(ROOT), str(ROOT / "tests")])
        ),
        "PYTHONDONTWRITEBYTECODE": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "TMPDIR": str(tmp_path),
    }
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), case, str(tmp_path)],
        env=env, cwd=tmp_path, capture_output=True, text=True, timeout=35, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("case", ["multipage", "blank", "corrupt", "encrypted"])
def test_pdf_reader_compatibility_is_resource_bounded(case, tmp_path):
    _run_bounded(case, tmp_path)


@pytest.mark.parametrize("case", ["corrupt", "encrypted", "blank"])
def test_unreadable_pdf_keeps_saved_styles_without_model_or_write(case, tmp_path):
    _run_bounded("app_" + case, tmp_path)


def _synthetic_pdf(kind: str) -> bytes:
    import io

    from pypdf import PdfReader, PdfWriter
    from test_reading import make_pdf

    if kind == "corrupt":
        return b"%PDF-1.4\noriginal incomplete synthetic fixture\n%%EOF\n"
    writer = PdfWriter()
    if kind != "blank":
        text = (
            "Original test sample. The caretaker opened a window. " * 10
            if kind == "style"
            else "First original page."
        )
        writer.add_page(PdfReader(io.BytesIO(make_pdf(text))).pages[0])
        writer.pages[0].compress_content_streams()
    writer.add_blank_page(width=612, height=792)
    if kind == "multipage":
        writer.add_page(PdfReader(io.BytesIO(make_pdf("Last original page."))).pages[0])
        writer.pages[-1].compress_content_streams()
    if kind == "encrypted":
        writer.encrypt("synthetic-test-password", algorithm="RC4-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _check_reader(case: str) -> None:
    from pypdf.errors import FileNotDecryptedError, PdfReadError

    from novel_ai.reading import (
        extract_reference,
        extract_reference_text,
        extract_reference_text_with_backend,
    )

    data = _synthetic_pdf(case)
    if case in {"corrupt", "encrypted"}:
        with pytest.raises((PdfReadError, FileNotDecryptedError, ValueError)):
            extract_reference("original.PDF", data)
        return
    expected = "First original page.\n\nLast original page." if case == "multipage" else ""
    result = extract_reference("original.PDF", data)
    assert result.text == expected
    assert result.backend == "pypdf"
    assert result.decoding is None
    assert extract_reference_text("original.pdf", data) == expected
    assert extract_reference_text_with_backend("original.pdf", data) == (expected, "pypdf")


def _check_app(case: str, tmp_path: Path) -> None:
    import copy

    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from novel_ai.provider import OpenAICompatibleProvider

    content = [_synthetic_pdf("style")]

    class Upload:
        name = "original-synthetic.pdf"

        def getvalue(self):
            return content[0]

    original_uploader = st.file_uploader
    calls = []

    def uploader(label, *args, **kwargs):
        return Upload() if label.startswith("上传参考文本") else original_uploader(label, *args, **kwargs)

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("PDF rejection must not contact a model")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(st, "file_uploader", uploader)
        patch.setattr(OpenAICompatibleProvider, "chat", forbidden)
        patch.chdir(tmp_path)
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        assert not at.exception
        semantic = next(c for c in at.checkbox if c.label == "使用当前模型做语义文体分析")
        semantic.uncheck()
        next(b for b in at.button if b.label == "分析并加入风格库").click().run()
        assert not at.exception and not at.error
        assert len(at.session_state["style_profiles"]) == 1
        previous = copy.deepcopy(at.session_state["style_profiles"])
        before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in (tmp_path / "data").rglob("*") if p.is_file()}
        assert any(name.endswith("style_profiles.json") for name in before)

        content[0] = _synthetic_pdf(case)
        next(c for c in at.checkbox if c.label == "使用当前模型做语义文体分析").check()
        next(b for b in at.button if b.label == "分析并加入风格库").click().run()
        assert calls == []
        assert at.session_state["style_profiles"] == previous
        assert at.session_state.get("style_pending") is None
        after = {str(p.relative_to(tmp_path)): p.read_bytes() for p in (tmp_path / "data").rglob("*") if p.is_file()}
        assert after == before
        if case == "blank":
            assert not at.exception and at.warning
        else:
            # Both the old and upgraded dependency expose these errors through
            # Streamlit's exception panel. This check proves rejection preserves
            # state; normalizing that pre-existing UI presentation is separate.
            assert at.error or at.exception
            if at.exception:
                expected_error = "startxref not found" if case == "corrupt" else "File has not been decrypted"
                assert len(at.exception) == 1
                assert at.exception[0].message == expected_error


if __name__ == "__main__":
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (12, 15))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**2, 8 * 1024**2))
    from novel_ai import reading

    # The dependency under review is the deterministic pypdf fallback.
    reading._advanced_extract = lambda *args: None
    scenario, directory = sys.argv[1:]
    if scenario.startswith("app_"):
        _check_app(scenario.removeprefix("app_"), Path(directory))
    else:
        _check_reader(scenario)
