from novel_ai.originality import (
    evaluate_originality,
    event_sequence_similarity,
    fuzzy_similarity,
    shingle_similarity,
)


class FixedEncoder:
    def encode(self, texts):
        return [[1.0, 0.0] if "相同" in text else [0.0, 1.0] for text in texts]


def test_exact_copy_triggers_lexical_and_event_layers():
    source = "第1章 警报响起，他发现密室，决定追杀叛徒。"
    result = evaluate_originality(source, [source])
    assert result.passed is False
    assert {"shingle", "fuzzy", "event_sequence"} <= {
        layer.name for layer in result.layers if layer.flagged
    }
    assert result.layers[2].available is False
    assert source not in str(result.to_dict())


def test_unrelated_text_passes_non_strict_without_embedding_backend():
    result = evaluate_originality(
        "山谷里下了一夜的大雪，商队明天才会进城。",
        ["海边的渔船在黄昏前返航，码头亮起了灯。"],
    )
    assert result.passed is True
    assert result.strict is False
    assert "embedding" in {layer.name for layer in result.layers}


def test_strict_mode_fails_closed_without_encoder():
    result = evaluate_originality("完全新的片段", ["另一段文本"], strict=True)
    assert result.passed is False
    assert any("strict" in note for note in result.notes)


def test_configured_encoder_runs_embedding_layer():
    result = evaluate_originality(
        "相同目标",
        ["相同参考"],
        encoder=FixedEncoder(),
        thresholds={"shingle": 1.1, "fuzzy": 1.1, "event_sequence": 1.1},
    )
    embedding = next(layer for layer in result.layers if layer.name == "embedding")
    assert embedding.available is True
    assert embedding.score == 1.0
    assert embedding.flagged is True
    assert result.passed is False


def test_event_sequence_uses_lcs_order_signal():
    score, left, right = event_sequence_similarity(
        "先发现线索，随后决定离开，最后失去证据。",
        "发现秘密后决定离开，但最终失去机会。",
    )
    assert left
    assert right
    assert score > 0.5
    assert shingle_similarity("甲乙丙丁甲乙", "甲乙丙丁甲乙") == 1.0
    assert fuzzy_similarity("abc", "abc") == 1.0


def test_empty_inputs_fail_closed():
    result = evaluate_originality("", ["参考"])
    assert result.passed is False
    assert result.layers == []


def test_originality_cli_runs_from_checkout(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).parents[1]
    target = tmp_path / "target.txt"
    reference = tmp_path / "reference.txt"
    output = tmp_path / "originality.json"
    target.write_text("山谷里下了一夜的大雪，商队明天才会进城。", encoding="utf-8")
    reference.write_text("海边的渔船在黄昏前返航，码头亮起了灯。", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "check_originality.py"),
            "--target",
            str(target),
            "--reference",
            str(reference),
            "--output",
            str(output),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] is True
    assert result.returncode == 0
