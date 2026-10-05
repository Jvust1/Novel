"""Regression expectations for first-chapter source identity; no model/network use."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from novel_ai import gpt_story_state as api


def started():
    value = api.create_state("synthetic-book-B")
    return api.transition(value, {
        "action": "start_chapter", "story_id": value.story_id,
        "base_story_revision": 0, "operation_id": "synthetic-start-first-chapter",
        "expected_state_sha256": api.state_fingerprint(value),
        "payload": {"chapter_id": "chapter-1"},
    })


def test_wrong_expected_book_is_rejected_at_revision_zero():
    with pytest.raises(api.StateError, match="story|source"):
        api.preflight_next_chapter_context(started(), [], 120000,
                                          expected_story_id="synthetic-book-A")


def test_wrong_expected_history_is_rejected_at_revision_zero():
    with pytest.raises(api.StateError, match="history|source"):
        api.preflight_next_chapter_context(started(), [], 120000,
                                          expected_history_sha256="0" * 64)


def cli(tmp_path, command, *extra):
    value = started()
    path = tmp_path / "synthetic-first-chapter.json"
    api.save_state(path, value)
    sources = tmp_path / "empty-sources.json"
    sources.write_text("[]\n", encoding="utf-8")
    checkout = Path(api.__file__).resolve().parents[1]
    options = ["--sources", str(sources), "--budget-bytes", "120000"] if command == "next-preflight" else []
    return subprocess.run([sys.executable, str(checkout / "scripts/story_state.py"),
        command, str(path), *options, *extra], capture_output=True, text=True, check=False, timeout=30,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def test_cli_wrong_expected_history_returns_failure(tmp_path):
    result = cli(tmp_path, "next-preflight", "--story-id", "synthetic-book-B",
                 "--expected-history-sha256", "0" * 64)
    assert result.returncode == 2, result.stdout


def test_default_empty_history_and_its_existing_hash_remain_unchanged():
    value = started()
    baseline = api.preflight_next_chapter_context(value, [], 120000)
    assert not baseline["blocked"]
    assert hashlib.sha256(json.dumps(baseline, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest() == (
        "1c58cebfa7ed6d5cb01f8e93b47a3dc8648654ae83aa7b404e74cfa2f8b9034f")
    digest = baseline["accepted_history"]["accepted_history_sha256"]
    assert digest == "2aae93342763c2168c37a0b215d036ceefc93c3a8da2ebef84c02f101c55204e"
    exact = api.preflight_next_chapter_context(value, [], 120000,
        expected_story_id=value.story_id, expected_history_sha256=digest)
    assert exact == baseline
    # Existing revision-zero contracts deliberately expose distinct hashes.
    assert api.rebuild_accepted_history(value)["accepted_history_sha256"] != digest


@pytest.mark.parametrize("kwargs", [
    {"expected_story_id": "synthetic-book-A"},
    {"expected_history_sha256": "0" * 64},
])
def test_control_rebuild_already_rejects_mismatched_expectations(kwargs):
    with pytest.raises(api.StateError):
        api.rebuild_accepted_history(started(), **kwargs)


def test_control_required_source_still_blocks():
    result = api.preflight_next_chapter_context(started(), [], 120000,
        required_sources=[{"source_id": "synthetic-required-document", "revision": 1}])
    assert result["blocked"]
    assert any("required source missing" in reason for reason in result["reasons"])


def test_control_small_budget_still_blocks():
    result = api.preflight_next_chapter_context(started(), [], 1)
    assert result["blocked"]


def test_control_cli_wrong_book_is_caught_by_loader(tmp_path):
    result = cli(tmp_path, "next-preflight", "--story-id", "synthetic-book-A")
    assert result.returncode == 2
    assert "different story" in result.stderr


def test_control_cli_history_command_checks_hash_at_revision_zero(tmp_path):
    result = cli(tmp_path, "accepted-history", "--story-id", "synthetic-book-B",
                 "--expected-history-sha256", "0" * 64)
    assert result.returncode == 2
    assert "stale" in result.stderr


def step(value, action, payload, serial):
    return api.transition(value, {
        "action": action, "story_id": value.story_id,
        "base_story_revision": value.revision,
        "operation_id": "synthetic-draft-control-" + str(serial),
        "expected_state_sha256": api.state_fingerprint(value), "payload": payload,
    })


def draft_ready():
    value = started()
    plan = api.artifact("An original synthetic scene plan", source_id="synthetic-plan",
                        location="synthetic-test://plan", revision=1)
    value = step(value, "set_plan", {"artifact": plan.model_dump(mode="json")}, 1)
    value = step(value, "accept_plan", {"confirmation": {
        "confirmed_by": "author", "confirmation_source": "synthetic-test://simulated-author-only",
        "story_id": value.story_id, "story_revision": 0, "chapter_id": "chapter-1",
        "plan_revision": 1, "plan_source_fingerprint": api.source_fingerprint(plan),
    }}, 2)
    draft = api.artifact("SYNTHETIC_CURRENT_DRAFT_SENTINEL", source_id="synthetic-draft",
                         location="synthetic-test://draft", revision=1)
    return step(value, "set_draft", {"artifact": draft.model_dump(mode="json")}, 3)


def test_control_current_draft_defaults_to_current_context():
    value = draft_ready()
    result = api.preflight_next_chapter_context(value, [], 120000)
    assert not result["blocked"]
    assert "SYNTHETIC_CURRENT_DRAFT_SENTINEL" in result["context_text"]
    assert result["accepted_history"]["history_chapter_ids"] == []


def test_control_current_draft_can_be_explicitly_excluded():
    value = draft_ready()
    result = api.preflight_next_chapter_context(value, [], 120000, include_current_draft=False)
    assert not result["blocked"]
    assert "SYNTHETIC_CURRENT_DRAFT_SENTINEL" not in result["context_text"]
    assert value.progress.draft is not None


def test_control_replan_does_not_leak_retained_old_draft():
    value = draft_ready()
    replacement = api.artifact("A changed synthetic plan", source_id="synthetic-plan",
                               location="synthetic-test://plan", revision=2)
    value = step(value, "set_plan", {"artifact": replacement.model_dump(mode="json")}, 4)
    assert value.progress.draft is not None
    result = api.preflight_next_chapter_context(value, [], 120000)
    assert not result["blocked"]
    assert "SYNTHETIC_CURRENT_DRAFT_SENTINEL" not in result["context_text"]


@pytest.mark.parametrize("field,value", [
    ("expected_story_id", ""), ("expected_story_id", False), ("expected_story_id", 0),
    ("expected_history_sha256", ""), ("expected_history_sha256", False),
    ("expected_history_sha256", 0), ("expected_history_sha256", "not-a-digest"),
])
def test_explicit_wrong_values_are_not_treated_as_omitted(field, value):
    state = started()
    before = state.model_dump()
    with pytest.raises(api.StateError):
        api.preflight_next_chapter_context(state, [], 120000, **{field: value})
    assert state.model_dump() == before


def test_explicit_none_retains_the_omitted_expectation_contract():
    state = started()
    expected = api.preflight_next_chapter_context(state, [], 120000)
    assert api.preflight_next_chapter_context(state, [], 120000,
        expected_story_id=None, expected_history_sha256=None) == expected


def test_cli_correct_empty_preflight_history_hash_succeeds(tmp_path):
    digest = api.preflight_next_chapter_context(started(), [], 120000)["accepted_history"]["accepted_history_sha256"]
    result = cli(tmp_path, "next-preflight", "--story-id", "synthetic-book-B",
                 "--expected-history-sha256", digest)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["accepted_history"]["accepted_history_sha256"] == digest


def test_current_draft_exclusion_still_obeys_explicit_choice():
    from test_gpt_story_state import planned, source, step
    state = step(planned(), "set_draft", {"artifact": source("UNACCEPTED-DRAFT-SENTINEL")})
    baseline = api.preflight_next_chapter_context(state, [], 120000, include_current_draft=False)
    digest = baseline["accepted_history"]["accepted_history_sha256"]
    result = api.preflight_next_chapter_context(state, [], 120000, include_current_draft=False,
        expected_story_id=state.story_id, expected_history_sha256=digest)
    assert result == baseline
    assert "UNACCEPTED-DRAFT-SENTINEL" not in result["context_text"]
