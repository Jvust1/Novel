"""Functional red baseline for the wording-similarity evidence panel."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def _run_app(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    return at


def _upload_evidence(at, files):
    uploader = at.file_uploader(key="reference_evidence_upload")
    uploader.set_value(files)
    at.run()


def test_wording_similarity_panel_baseline_functional_red(monkeypatch, tmp_path):
    """The requested panel must exist before its production implementation is added."""
    at = _run_app(monkeypatch, tmp_path)
    _upload_evidence(at, [
        ("source.txt", "Chapter 1\\nnight radio 电台在雨夜响起。\\n".encode("utf-8"), "text/plain"),
        ("source.md", "## Chapter 2\\n雨夜的 radio signal 断断续续。\\n".encode("utf-8"), "text/markdown"),
    ])
    at.text_input(key="reference_evidence_query").set_value("night radio 电台").run()
    at.button(key="btn_reference_evidence").click().run()
    assert not at.exception

    # These controls are intentionally absent on the frozen #89 implementation.
    at.text_area(key="reference_wording_draft").set_value("夜里的电台在雨声中响起。").run()
    at.checkbox(key="reference_wording_match_0").check().run()
    at.button(key="btn_reference_wording_check").click().run()
    assert not at.exception
    assert at.session_state["reference_wording_result"]["matches"]

