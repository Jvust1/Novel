"""Frozen v2 analysis input and live v3 integration are separate contracts."""
import json
from copy import deepcopy

import pytest
from test_accepted_archive_writing import ready_archive

from novel_ai import gpt_story_state as state

# Synthetic PR54 archive only. These values predate the v3 metric upgrade;
# the existing five PR54 whole-result hashes independently bind this fixture.
FROZEN_VOICE_V2 = {
    "林青": {
        "attribution_version": 2, "line_count": 2, "avg_line_chars": 6,
        "short_line_ratio": 1.0, "long_line_ratio": 0.0, "question_ratio": 0.5,
        "exclamation_ratio": 0.0, "ellipsis_ratio": 0.0,
        "first_person_density": 0.0, "second_person_density": 0.0833,
        "ending_particles": {},
    },
    "木禾": {
        "attribution_version": 2, "line_count": 1, "avg_line_chars": 5,
        "short_line_ratio": 1.0, "long_line_ratio": 0.0, "question_ratio": 0.0,
        "exclamation_ratio": 0.0, "ellipsis_ratio": 0.0,
        "first_person_density": 0.0, "second_person_density": 0.0,
        "ending_particles": {},
    },
}
FROZEN_BASELINE_V2 = {
    name: {**deepcopy(metrics), "avg_line_chars": float(metrics["avg_line_chars"]), "chapter_count": 1}
    for name, metrics in FROZEN_VOICE_V2.items()
}


@pytest.mark.parametrize("variant", ["history", "default", "omit", "no_auto", "small"])
def test_live_v3_rebuild_keeps_accepted_identity_and_source_bytes(tmp_path, variant):
    path = ready_archive(tmp_path)
    before = path.read_bytes()
    value = state.load_state(path, expected_story_id="synthetic-story")
    if variant == "history":
        result = state.rebuild_accepted_history(value)
        history = compact = result
    else:
        options = {"include_current_draft": False} if variant == "omit" else {"history_source_limit": 0} if variant == "no_auto" else {}
        result = state.preflight_next_chapter_context(value, [], 1000 if variant == "small" else 200000, **options)
        history = result["accepted_history"]
        marker = "ACCEPTED HISTORY ONLY. Rebuilt from verified author-accepted versions; candidates are excluded.\n"
        compact = json.loads(result["context_text"].split(marker, 1)[1])
        assert result["blocked"] is (variant == "small")

    expected_voice = deepcopy(FROZEN_VOICE_V2)
    expected_baseline = deepcopy(FROZEN_BASELINE_V2)
    for metrics in (expected_voice, expected_baseline):
        for row in metrics.values():
            row["attribution_version"] = 3
        metrics["林青"]["ending_particles"] = {"吧": 1, "吗": 1}
    assert compact["voice_baseline"] == expected_baseline
    assert len(compact["recent_chapters"]) == 1
    assert compact["recent_chapters"][0]["voice_dna"] == expected_voice
    if variant == "history":
        assert result["accepted_chapters"] == result["recent_chapters"]
    assert history["history_chapter_ids"] == ["ch-1"]
    assert history["accepted_history_sha256"] == "463db24b6da2489046490061e49f72044e74406a67a2289472d9e3fb259af284"
    assert path.read_bytes() == before
