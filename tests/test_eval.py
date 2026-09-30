import json
from pathlib import Path

import pytest

from novel_ai.context import ContextAssembler
from novel_ai.engine import NovelEngine, parse_json_object
from novel_ai.eval import (
    RUBRIC_KEYS,
    VARIANTS,
    aggregate_scores,
    load_benchmark,
    load_scores,
    make_scoring_sheet,
    render_scoring_pack,
    run_case,
    seed_store_from_case,
)
from novel_ai.models import ChapterPlan, StoryBible
from novel_ai.provider import ProviderConfig


class FakeProvider:
    """Scripted provider: no network. Returns a minimal valid plan/draft/review."""

    def __init__(self):
        self.calls: list[dict] = []
        self.review_verdict = "revise"

    def chat(self, messages, *, temperature=0.8, max_tokens=None, response_format=None):
        self.calls.append({"messages": messages, "response_format": response_format})
        system = messages[0]["content"]
        if response_format and "章节策划" in system:
            return json.dumps(
                {
                    "chapter_title": "测试章",
                    "chapter_promise": "承诺",
                    "tension_curve": "先抑后扬",
                    "scenes": [
                        {
                            "scene_no": 1,
                            "objective": "目标",
                            "opposition": "阻力",
                            "choice": "选择",
                            "cost": "代价",
                            "state_change": "变化",
                        }
                    ],
                    "must_not_happen": [],
                },
                ensure_ascii=False,
            )
        if response_format and "严苛的网络小说章节编辑" in system:
            return json.dumps({"verdict": self.review_verdict, "issues": []}, ensure_ascii=False)
        if response_format:
            return "{}"
        return "正文第一段。\n\n正文第二段。"


def make_engine() -> tuple[NovelEngine, FakeProvider]:
    provider = FakeProvider()
    return NovelEngine(provider), provider


def test_load_benchmark_verifies_frozen_hashes():
    cases = load_benchmark("benchmarks")
    assert {c.case_id for c in cases} == {"urban_dispute", "xuanhuan_residual", "mystery_calls"}
    for case in cases:
        assert case.pre_history["chapter_summaries"]
        assert case.data["characters"]


def test_load_benchmark_rejects_tampered_case(tmp_path):
    import shutil

    shutil.copytree("benchmarks", tmp_path / "benchmarks")
    victim = tmp_path / "benchmarks" / "cases" / "urban_dispute.json"
    data = json.loads(victim.read_text(encoding="utf-8"))
    data["chapter_goal"] = "被篡改的目标"
    victim.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with pytest.raises(ValueError, match="冻结"):
        load_benchmark(tmp_path / "benchmarks")


def test_variants_only_differ_in_memory_layer(tmp_path):
    engine, provider = make_engine()
    case = load_benchmark("benchmarks")[0]
    run_case(engine, case, "A_baseline", tmp_path / "a")
    run_case(engine, case, "B_memory", tmp_path / "b")
    # 每次 run_case 产生 plan + draft 两次调用；取 B 的 plan 调用
    plan_calls = [c for c in provider.calls if "章节策划编辑" in c["messages"][0]["content"]]
    assert len(plan_calls) == 2
    a_user, b_user = plan_calls[0]["messages"][1]["content"], plan_calls[1]["messages"][1]["content"]
    assert "【Canon 长期记忆" not in a_user
    assert "【Canon 长期记忆" in b_user
    assert "开放伏笔" in b_user


def test_run_case_records_completion_gate(tmp_path):
    engine, _ = make_engine()
    case = load_benchmark("benchmarks")[0]
    row = run_case(engine, case, "A_baseline", tmp_path / "gate")
    assert row["completion_gate"]["status"] == "FAIL"
    assert row["completion_gate"]["method"]["principle"] == "actual bytes on disk outrank model self-report"


def test_seed_store_materializes_pre_history(tmp_path):
    case = load_benchmark("benchmarks")[0]
    store = seed_store_from_case(case, tmp_path, "bench")
    state = store.load_story_state("bench")
    assert state["facts"] == case.pre_history["facts"]
    assert len(store.recent_chapter_summaries("bench", limit=4)) == 3
    ctx = ContextAssembler(store, "bench").assemble(recent_limit=2)
    assert ctx.canon_block and ctx.active_block
    assert ctx.recall_block  # limit=2 < 3 条摘要，最早的章节进入 Recall


def test_scoring_sheet_roundtrip_and_aggregation(tmp_path):
    run_record = {
        "run_id": "run-test",
        "cases": [
            {"case_id": "urban_dispute", "variant": "A_baseline"},
            {"case_id": "urban_dispute", "variant": "B_memory"},
        ],
    }
    sheet = make_scoring_sheet(run_record, tmp_path / "sheet.csv")
    rows = list(csv_rows(sheet))
    assert len(rows) == 2 * len(RUBRIC_KEYS)

    filled = tmp_path / "filled.csv"
    # 给第一行（A_baseline 的 plot_pull）填 5 分做聚合烟囱测试
    text = sheet.read_text(encoding="utf-8-sig")
    assert text.count("情节吸引力,,") == 2
    text = text.replace("情节吸引力,,", "情节吸引力,5,", 1)
    filled.write_text(text, encoding="utf-8")
    scores = load_scores(filled)
    assert len(scores) == 1 and scores[0]["score"] == 5
    assert scores[0]["variant"] == "A_baseline"
    assert aggregate_scores(scores)["by_group"]["urban_dispute|A_baseline"]["overall"] == 5.0


def csv_rows(path: Path):
    import csv

    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_parse_json_object_tolerant():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('前缀 {"a": {"b": 2}} 后缀') == {"a": {"b": 2}}


def test_provider_config_defaults():
    cfg = ProviderConfig(base_url="http://x", model="m")
    assert cfg.timeout == 180.0


def test_run_rereviews_after_repair():
    engine, provider = make_engine()
    provider.review_verdict = "revise"
    result = engine.run(
        bible=StoryBible(),
        outline="纲",
        chapter_goal="目标",
        characters=[],
        recent_summaries=[],
        review=True,
        auto_repair=True,
    )
    assert result.revised is not None
    assert result.review_after_repair is not None
    assert result.final_text == result.revised
    assert result.completion_gate_report is not None
    kinds = []
    for call in provider.calls:
        system = call["messages"][0]["content"]
        if "章节策划" in system:
            kinds.append("plan")
        elif "严苛的网络小说章节编辑" in system:
            kinds.append("review")
        else:
            kinds.append("draft/repair")
    assert kinds == ["plan", "draft/repair", "review", "draft/repair", "review"]


def test_run_skips_repair_and_rereview_on_pass():
    engine, provider = make_engine()
    provider.review_verdict = "pass"
    result = engine.run(
        bible=StoryBible(),
        outline="纲",
        chapter_goal="目标",
        characters=[],
        recent_summaries=[],
        review=True,
        auto_repair=True,
    )
    assert result.revised is None
    assert result.review_after_repair is None
    assert result.final_text == result.draft
    assert result.completion_gate_report is not None


def test_render_scoring_pack_includes_goal_texts_and_rubric(tmp_path):
    run_dir = tmp_path / "run-x"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_id": "run-x",
                "provider_note": "model=fake",
                "cases": [
                    {"case_id": "urban_dispute", "variant": "A_baseline", "extra_context_chars": 0},
                    {"case_id": "urban_dispute", "variant": "B_memory", "extra_context_chars": 123},
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "urban_dispute__A_baseline.txt").write_text("甲的正文。", encoding="utf-8")
    (run_dir / "urban_dispute__B_memory.txt").write_text("乙的正文。", encoding="utf-8")
    out = render_scoring_pack(run_dir)
    pack = out.read_text(encoding="utf-8")
    assert "评分包 · run-x" in pack
    assert "模型：`model=fake`" in pack
    for key in RUBRIC_KEYS:
        assert key in pack
    assert "甲的正文。" in pack and "乙的正文。" in pack
    assert "刘聪" in pack  # 冻结用例的章纲细节进入评分包供对照
    assert pack.index("A_baseline") < pack.index("B_memory")
