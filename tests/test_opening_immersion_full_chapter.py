"""Preserve full chapter identity and record exactly what the opening trial changes.

This is reproducibility/continuity validation, not a literary-quality score.
"""
import hashlib
import json
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / "writing_demos/plugin-first-chapter-20261001"
TRIAL = DEMO / "opening-immersion-trial/full-chapter-v2"


def test_full_chapter_opening_changes_are_exact_and_reversible():
    original = (DEMO / "chapter-001.md").read_bytes()
    record = json.loads((TRIAL / "provenance.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(original).hexdigest() == record["source"]["sha256"]
    first = original.decode("utf-8")
    assert (TRIAL / "reader/01.md").read_text(encoding="utf-8") == first

    expected = first
    for row in record["changes"]:
        assert expected.count(row["before"]) == 1, row["why"]
        expected = expected.replace(row["before"], row["after"], 1)

    second = (TRIAL / "reader/02.md").read_text(encoding="utf-8")
    assert second == expected
    assert second != first
    assert len(first) == len(second)  # Controls a length confound, not prose quality.
    marker = record["source"]["first_scene_end_marker"]
    assert first.count(marker) == second.count(marker) == 1
    assert first.split(marker, 1)[1] == second.split(marker, 1)[1]
    for item in record["protected_markers"]:
        assert item in first and item in second
    for value in ("韩平", "吕阿棉", "孟川", "周福"):
        assert first.count(value) == second.count(value)
    assert record["evaluation"]["human_readers"] == 0
    assert record["evaluation"]["human_ratings"] == []
    assert record["evaluation"]["author_accepted"] is None
    assert record["evaluation"]["canon_advanced"] is False


def test_reader_material_does_not_reveal_origins():
    form = (TRIAL / "reader/rating-form.md").read_text(encoding="utf-8")
    assert "最想继续读哪份" in form
    assert "01→02" in form and "02→01" in form
    for name in ("01.md", "02.md"):
        text = (TRIAL / "reader" / name).read_text(encoding="utf-8")
        for forbidden in ("baseline", "candidate", "原稿：", "改稿：", "AI生成"):
            assert forbidden not in text
