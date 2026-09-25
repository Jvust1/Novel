import csv
import json
from pathlib import Path

import pytest

from novel_ai.blind_scoring import (
    aggregate_blind_scores,
    blind_score_status,
    load_blind_scores,
    render_blind_scoring_pack,
)
from novel_ai.eval import RUBRIC_KEYS


def _make_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run-x"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "run-x",
                "provider_note": "model=fake-should-stay-hidden",
                "cases": [
                    {
                        "case_id": "urban_dispute",
                        "variant": "A_baseline",
                        "extra_context_chars": 0,
                    },
                    {
                        "case_id": "urban_dispute",
                        "variant": "B_memory",
                        "extra_context_chars": 123,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "urban_dispute__A_baseline.txt").write_text("甲的正文。", encoding="utf-8")
    (run_dir / "urban_dispute__B_memory.txt").write_text("乙的正文。", encoding="utf-8")
    return run_dir


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_render_blind_pack_hides_variant_and_provider_labels(tmp_path):
    run_dir = _make_run(tmp_path)
    outputs = render_blind_scoring_pack(run_dir)

    pack = outputs["pack"].read_text(encoding="utf-8")
    mapping = json.loads(outputs["map"].read_text(encoding="utf-8"))
    rows = _rows(outputs["sheet"])

    assert "A_baseline" not in pack
    assert "B_memory" not in pack
    assert "model=fake-should-stay-hidden" not in pack
    assert "extra_context_chars" not in pack
    assert "甲的正文。" in pack and "乙的正文。" in pack
    assert {sample["variant"] for sample in mapping["samples"]} == {
        "A_baseline",
        "B_memory",
    }
    for sample in mapping["samples"]:
        assert sample["sample_id"] in pack

    assert len(rows) == 2 * len(RUBRIC_KEYS)
    assert "variant" not in rows[0]
    assert {"sample_id", "score", "rationale", "anchor"} <= set(rows[0])


def test_blind_render_is_deterministic_for_same_run(tmp_path):
    run_dir = _make_run(tmp_path)
    first = render_blind_scoring_pack(run_dir)
    before = {name: path.read_bytes() for name, path in first.items()}
    second = render_blind_scoring_pack(run_dir)
    after = {name: path.read_bytes() for name, path in second.items()}
    assert before == after


def test_blind_scores_unblind_and_require_complete_grid(tmp_path):
    run_dir = _make_run(tmp_path)
    outputs = render_blind_scoring_pack(run_dir)
    rows = _rows(outputs["sheet"])

    rows[0]["score"] = "5"
    rows[0]["rationale"] = "冲突建立迅速。"
    with outputs["sheet"].open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    scored = load_blind_scores(outputs["sheet"], outputs["map"])
    assert len(scored) == 1
    assert scored[0]["score"] == 5
    assert scored[0]["notes"] == "冲突建立迅速。"
    assert scored[0]["variant"] in {"A_baseline", "B_memory"}

    status = blind_score_status(outputs["sheet"], outputs["map"])
    assert status["scored_rows"] == 1
    assert status["expected_rows"] == 2 * len(RUBRIC_KEYS)
    assert not status["complete"]
    with pytest.raises(ValueError, match="盲化评分未完成"):
        aggregate_blind_scores(outputs["sheet"], outputs["map"])

    for row in rows:
        row["score"] = "4"
        row["rationale"] = row["rationale"] or "可接受。"
    with outputs["sheet"].open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = aggregate_blind_scores(outputs["sheet"], outputs["map"])
    assert summary["blind_scoring"]["complete"] is True
    assert summary["blind_scoring"]["scored_rows"] == 2 * len(RUBRIC_KEYS)
    assert summary["variant_overall"]["A_baseline"] == 4.0
    assert summary["variant_overall"]["B_memory"] == 4.0
    assert summary["deltas"]["B_minus_A"] == 0.0


def test_blind_scores_reject_unknown_sample_id(tmp_path):
    run_dir = _make_run(tmp_path)
    outputs = render_blind_scoring_pack(run_dir)
    rows = _rows(outputs["sheet"])
    rows[0]["sample_id"] = "S-TAMPERED"
    rows[0]["score"] = "3"
    with outputs["sheet"].open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="未知 sample_id"):
        load_blind_scores(outputs["sheet"], outputs["map"])
