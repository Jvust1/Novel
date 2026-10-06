"""Real AppTest coverage for the session-only wording check."""

import hashlib
import json
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
    assert hasattr(uploader, "set_value"), "installed AppTest lacks real uploader support"
    uploader.set_value(files)
    at.run()


def _query(at, query):
    at.text_input(key="reference_evidence_query").set_value(query).run()
    at.button(key="btn_reference_evidence").click().run()
    assert not at.exception
    return at.session_state["reference_evidence_result"]


def _downloads(at, key):
    return [item for item in at.download_button if item.key == key]


def _check(at, match_id, draft):
    at.text_area(key="reference_wording_draft").set_value(draft).run()
    at.checkbox(key=f"reference_wording_match_{match_id}").check().run()
    at.button(key="btn_reference_wording_check").click().run()
    assert not at.exception
    return at.session_state["reference_wording_result"]


def _sources():
    first = "# Chapter 1\nnight radio 电台在雨夜响起。\n".encode("utf-8")
    second = "## Chapter 2\n雨夜的 radio signal 断断续续。\n".encode("utf-8")
    return [
        ("source.txt", first, "text/plain"),
        ("source.md", second, "text/markdown"),
    ], first, second


def test_reference_wording_ui_uses_real_uploads_and_deterministic_metric(
    monkeypatch, tmp_path
):
    from novel_ai.provider import OpenAICompatibleProvider
    from novel_ai.reading import extract_reference

    def fail_provider(*args, **kwargs):
        raise AssertionError("wording check must not call a provider")

    monkeypatch.setattr(OpenAICompatibleProvider, "chat", fail_provider)
    at = _run_app(monkeypatch, tmp_path)
    files, first, _second = _sources()
    _upload_evidence(at, files)
    evidence = _query(at, "night radio 电台")
    assert evidence["matches"]
    selected = evidence["matches"][0]
    assert selected["source_filename"] == "source.txt"
    assert selected["raw_source_sha256"] == hashlib.sha256(first).hexdigest()
    assert selected["chapter"] == "Chapter 1"
    assert selected["offset_basis"] == "sanitized-extracted-unicode-codepoints"
    extracted = extract_reference("source.txt", first, encoding=None)
    assert selected["extracted_text_sha256"] == hashlib.sha256(extracted.text.encode("utf-8")).hexdigest()
    assert extracted.text[selected["start"]:selected["end"]] == selected["excerpt"]
    assert selected["start"] < selected["end"]
    assert selected["id"]

    result = _check(at, selected["id"], selected["excerpt"])
    assert result["advisory_only"] is True
    assert result["metric"]["name"] == "normalized_levenshtein_similarity"
    assert result["metric"]["upstream_commit"] == "db6e504539a9c895180b266a06b36a32cb6029ee"
    assert result["matches"][0]["similarity"] == 1.0
    assert result["matches"][0]["stable_id"] == selected["id"]
    assert result["matches"][0]["start"] == selected["start"]
    assert result["matches"][0]["raw_source_sha256"] == selected["raw_source_sha256"]
    assert _downloads(at, "download_reference_wording")
    assert any(
        "normalized_levenshtein_similarity" in json.dumps(item.value, ensure_ascii=False)
        for item in at.json
    )

    repeated = _check(at, selected["id"], selected["excerpt"])
    assert repeated["matches"][0]["stable_id"] == result["matches"][0]["stable_id"]
    assert repeated["matches"][0]["similarity"] == result["matches"][0]["similarity"]

    for path in tmp_path.rglob("*"):
        if path.is_file():
            body = path.read_bytes()
            assert b"night radio" not in body
            assert "夜里的电台".encode("utf-8") not in body


def test_reference_wording_scores_partial_and_unrelated_text(
    monkeypatch, tmp_path
):
    at = _run_app(monkeypatch, tmp_path)
    files, _first, _second = _sources()
    _upload_evidence(at, files)
    evidence = _query(at, "night radio")
    selected = evidence["matches"][0]

    partial = _check(at, selected["id"], "night radio")
    partial_score = partial["matches"][0]["similarity"]
    assert 0.0 < partial_score < 1.0

    unrelated = _check(at, selected["id"], "QZXQZXQZX")
    assert unrelated["matches"][0]["similarity"] == 0.0


def test_reference_wording_server_rejects_2049_char_draft(monkeypatch, tmp_path):
    at = _run_app(monkeypatch, tmp_path)
    files, _first, _second = _sources()
    _upload_evidence(at, files)
    evidence = _query(at, "night radio")
    selected = evidence["matches"][0]

    at.checkbox(key=f"reference_wording_match_{selected['id']}").check().run()
    _check(at, selected["id"], selected["excerpt"])
    assert _downloads(at, "download_reference_wording")

    overlong = "x" * 2049
    prior_value = at.session_state["reference_wording_draft"]
    at.text_area(key="reference_wording_draft").set_value(overlong).run()
    stable_value = at.session_state["reference_wording_draft"]
    assert isinstance(stable_value, str)
    if stable_value == overlong:
        stable_behavior = "accepted-for-server"
    elif stable_value == overlong[:2048]:
        stable_behavior = "client-truncated-at-2048"
    elif stable_value in {prior_value, ""}:
        stable_behavior = "rejected-before-submit"
    else:
        raise AssertionError(
            f"unexpected stable overlong value length: {len(stable_value)}"
        )
    assert stable_behavior in {
        "accepted-for-server",
        "client-truncated-at-2048",
        "rejected-before-submit",
    }

    # AppTest's widget transport may enforce max_chars before submit. Inject the
    # 2049-character value only after recording that real widget behavior so the
    # application handler itself is exercised at its server-side guard.
    at.session_state["reference_wording_draft"] = overlong
    assert at.session_state["reference_wording_draft"] == overlong
    at.button(key="btn_reference_wording_check").click().run()
    assert not at.exception
    assert any("超过 2048" in item.value for item in at.error)
    assert "reference_wording_result" not in at.session_state
    assert not _downloads(at, "download_reference_wording")


def test_reference_wording_invalidates_old_result_on_edit_failure_and_project_switch(
    monkeypatch, tmp_path
):
    at = _run_app(monkeypatch, tmp_path)
    files, _first, _second = _sources()
    _upload_evidence(at, files)
    evidence = _query(at, "night radio")
    selected = evidence["matches"][0]
    _check(at, selected["id"], selected["excerpt"])
    assert _downloads(at, "download_reference_wording")

    at.text_area(key="reference_wording_draft").set_value("编辑后的新片段").run()
    assert "reference_wording_result" not in at.session_state
    assert not _downloads(at, "download_reference_wording")

    at.checkbox(key=f"reference_wording_match_{selected['id']}").uncheck().run()
    at.button(key="btn_reference_wording_check").click().run()
    assert not at.exception
    assert any("措辞相近检查未完成" in item.value for item in at.error)
    assert "reference_wording_result" not in at.session_state
    assert not _downloads(at, "download_reference_wording")

    at.text_input(key="project_name").set_value("OtherBook").run()
    assert "reference_evidence_result" not in at.session_state
    assert "reference_wording_result" not in at.session_state
    assert not _downloads(at, "download_reference_wording")

    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert "编辑后的新片段".encode("utf-8") not in path.read_bytes()

