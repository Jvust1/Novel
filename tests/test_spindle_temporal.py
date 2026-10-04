from novel_ai.spindle_temporal import (
    TemporalSceneInput,
    scan_temporal_coherence,
    temporal_coherence_report,
)


def test_detects_unmarked_forward_jump():
    hits = scan_temporal_coherence(
        TemporalSceneInput("清晨他离开客栈。夜里，他已经站在城门外。")
    )
    assert any(hit.kind == "temporal_teleport" for hit in hits)


def test_detects_unmarked_backward_drift():
    hits = scan_temporal_coherence(
        TemporalSceneInput("夜里他听见钟声。清晨，他又回到同一间屋里。")
    )
    assert any(hit.kind == "temporal_drift" for hit in hits)


def test_transition_and_memory_suppress_advisory():
    assert not scan_temporal_coherence(
        TemporalSceneInput("清晨他出门。几个小时后，夜里才回到客栈。")
    )
    assert not scan_temporal_coherence(
        TemporalSceneInput("夜里他望着灯火，回忆起清晨离开村子的情景。")
    )


def test_declared_span_is_reported_without_hard_failure():
    report = temporal_coherence_report(
        "清晨他开始赶路。夜里他仍在山中。",
        duration_days=2,
    )
    assert report["advisory_only"] is True
    assert any(item["kind"] == "unrendered_declared_span" for item in report["hits"])


def test_non_linear_and_coarse_scenes_are_skipped():
    assert not scan_temporal_coherence(
        TemporalSceneInput("夜里。清晨。", temporal_mode="flashback")
    )
    assert not scan_temporal_coherence(
        TemporalSceneInput("夜里。清晨。", precision="week")
    )
