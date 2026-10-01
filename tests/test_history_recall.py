"""Synthetic, local-only regression pilot for the adapted LangChain MMR path."""
from __future__ import annotations

import json
from copy import deepcopy
from math import nan

import pytest

from novel_ai._vendor.langchain_mmr import maximal_marginal_relevance
from novel_ai.context import ContextAssembler
from novel_ai.engine import NovelEngine
from novel_ai.history_recall import select_history
from novel_ai.models import StoryBible
from novel_ai.orchestration import ProviderRouter, ProviderTarget, RouterConfig
from novel_ai.provider import ProviderConfig
from novel_ai.routed_engine import RoutedNovelEngine
from novel_ai.storage import ProjectStore
from novel_ai.token_budget import TokenCounter


QUERY = "沈青拿仓库钥匙，林澄查账本。"
SUMMARIES = [
    {"chapter_id": "001", "summary": "仓库钥匙在沈青手里，仓库门一直锁着。"},
    {"chapter_id": "002", "summary": "仓库钥匙仍在沈青手里，仓库门一直锁着。"},
    {"chapter_id": "003", "summary": "账本已经交给林澄，林澄在码头等候。"},
    {"chapter_id": "004", "summary": "雨夜天色忽然暗了。"},
]


def test_mmr_prefers_diversity_after_relevance_and_keeps_ties_stable():
    pair = [[1, .99, .1], [.99, 1, .1], [.1, .1, 1]]
    similarity = lambda i, j: pair[i][j]
    assert maximal_marginal_relevance([.9, .89, .7], similarity, k=2) == [0, 2]
    assert maximal_marginal_relevance([.9, .89, .7], similarity, lambda_mult=1, k=2) == [0, 1]
    assert maximal_marginal_relevance([1, 1, 1], similarity, k=5) == [0, 2, 1]
    assert maximal_marginal_relevance([], similarity) == []
    assert maximal_marginal_relevance([1], similarity, k=0) == []


@pytest.mark.parametrize("value", [-.1, 1.1, nan])
def test_mmr_rejects_invalid_lambda(value):
    with pytest.raises(ValueError):
        maximal_marginal_relevance([1], lambda i, j: 0, lambda_mult=value)


def test_mmr_rejects_nonfinite_scores():
    with pytest.raises(ValueError):
        maximal_marginal_relevance([nan], lambda i, j: 0)
    with pytest.raises(ValueError):
        maximal_marginal_relevance([1, .8], lambda i, j: nan)


def test_chinese_recall_chooses_two_different_plot_threads_without_mutation():
    before = deepcopy(SUMMARIES)
    selected, report = select_history(QUERY, SUMMARIES, limit=2)
    assert [row["chapter_id"] for row in selected] == ["001", "003"]
    assert SUMMARIES == before
    assert report["candidate_count"] == 3
    assert "账本" not in json.dumps(report, ensure_ascii=False)
    assert len(report["selected"][0]["summary_sha256"]) == 64
    assert select_history(QUERY, SUMMARIES, limit=2) == (selected, report)


@pytest.mark.parametrize("query", ["", "完全无关的星球"])
def test_no_relevance_does_not_invent_a_recall_hit(query):
    selected, report = select_history(query, SUMMARIES)
    assert selected == []
    assert report["candidate_count"] == 0


def test_candidate_pool_is_bounded():
    rows = [{"chapter_id": str(i), "summary": "仓库钥匙"} for i in range(100)]
    selected, report = select_history("仓库钥匙", rows)
    assert len(selected) == 8
    assert report["candidate_count"] == 64
    with pytest.raises(ValueError):
        select_history(QUERY, rows, candidate_limit=65)


def make_store(tmp_path):
    store = ProjectStore(tmp_path)
    for row in SUMMARIES:
        store.save_extraction("P", row)
    store.save_story_state("P", {
        "facts": ["钥匙不得复制"],
        "foreshadowing": [{"id": "ledger", "description": "账本少了一页", "status": "planted"}],
        "open_threads": [],
    })
    return store


def test_context_opt_in_preserves_canon_active_and_recent_memory(tmp_path):
    store = make_store(tmp_path)
    assembler = ContextAssembler(store, "P", recall_char_budget=90)
    baseline = assembler.assemble(recent_limit=1)
    diverse = assembler.assemble(recent_limit=1, recall_query=QUERY)
    assert baseline.recall_report is None
    assert diverse.canon_block == baseline.canon_block
    assert diverse.active_block == baseline.active_block
    assert diverse.recent_summaries == baseline.recent_summaries == [SUMMARIES[3] | {"chapter_title": ""}]
    assert "001" in diverse.recall_block and "003" in diverse.recall_block
    assert "002" not in diverse.recall_block and "004" not in diverse.recall_block
    assert len(diverse.recall_block) <= 90
    assert diverse.recall_report["included_chapter_ids"] == ["001", "003"]


def test_zero_recent_limit_still_permits_explicit_history_recall(tmp_path):
    context = ContextAssembler(make_store(tmp_path), "P").assemble(recent_limit=0, recall_query=QUERY)
    assert context.recent_summaries == []
    assert "001" in context.recall_block


@pytest.mark.parametrize("budget", [0, 1, 30])
def test_small_character_budgets_do_not_emit_partial_facts(tmp_path, budget):
    context = ContextAssembler(make_store(tmp_path), "P", recall_char_budget=budget).assemble(recent_limit=1, recall_query=QUERY)
    assert context.recall_block == ""
    assert context.recall_report["included_chapter_ids"] == []


def test_complete_prompt_respects_token_and_character_limits(tmp_path):
    counter = TokenCounter(fallback_chars_per_token=1)
    context = ContextAssembler(make_store(tmp_path), "P", recall_char_budget=1000,
                               token_counter=counter, recall_token_budget=80).assemble(recent_limit=1, recall_query=QUERY)
    assert 0 < counter.count(context.recall_block) <= 80
    assert len(context.recall_block) <= 1000


class PilotProvider:
    """Tests the actual pipeline, while making no model/network request."""
    def __init__(self, name, calls):
        self.name, self.calls = name, calls
        self.reviews = 0

    def chat(self, messages, **kwargs):
        system = messages[0]["content"]
        if "章节策划" in system:
            stage, output = "plan", json.dumps({"chapter_title": "仓库", "scenes": []})
        elif "严苛的网络小说章节编辑" in system:
            self.reviews += 1
            stage = "review"
            output = json.dumps({"verdict": "revise" if self.reviews == 1 else "pass", "issues": []})
        elif "局部修订编辑" in system:
            stage, output = "repair", "沈青收好钥匙。林澄翻开账本。"
        else:
            stage, output = "draft", "沈青走进仓库。林澄翻开账本。"
        self.calls.append((self.name, stage, messages))
        return output


@pytest.mark.parametrize("routed", [False, True])
def test_generate_review_repair_rereview_all_receive_selected_history(tmp_path, routed):
    context = ContextAssembler(make_store(tmp_path), "P", recall_char_budget=90).assemble(recent_limit=1, recall_query=QUERY)
    calls = []
    writer = PilotProvider("writer", calls)
    if routed:
        router = ProviderRouter(RouterConfig(local=ProviderConfig("http://unused", "unused")))
        router._targets["local"] = ProviderTarget(name="local", provider=writer)
        router._targets["reviewer"] = ProviderTarget(name="reviewer", provider=PilotProvider("reviewer", calls))
        engine = RoutedNovelEngine(router)
    else:
        engine = NovelEngine(writer)
    result = engine.run(bible=StoryBible(), outline="开门取证", chapter_goal=QUERY, characters=[],
                        extra_context=context.prompt_sections(), recent_summaries=context.recent_summaries,
                        review=True, auto_repair=True)
    assert [stage for _, stage, _ in calls] == ["plan", "draft", "review", "repair", "review"]
    for _, _, messages in calls:
        prompt = messages[-1]["content"]
        assert "仓库钥匙在沈青手里" in prompt
        assert "账本已经交给林澄" in prompt
        assert "钥匙不得复制" in prompt
    assert result.final_text == "沈青收好钥匙。林澄翻开账本。"
    assert result.review_after_repair is not None
    if routed:
        assert [name for name, _, _ in calls] == ["writer", "writer", "reviewer", "writer", "reviewer"]


def test_review_false_never_adds_an_unrequested_review_call():
    calls = []
    result = NovelEngine(PilotProvider("writer", calls)).run(
        bible=StoryBible(), outline="纲", chapter_goal=QUERY, characters=[], review=False,
        auto_repair=True, extra_context="已有事实",
    )
    assert [stage for _, stage, _ in calls] == ["plan", "draft"]
    assert result.review is None and result.review_after_repair is None


def test_late_fact_is_preserved_as_a_complete_marked_sentence(tmp_path):
    summary = "村民到集市买米，顺路去看灯会。" * 8 + "仓库钥匙不是沈青拿走的。"
    store = ProjectStore(tmp_path)
    store.save_extraction("P", {"chapter_id": "001", "summary": summary})
    context = ContextAssembler(store, "P", recall_summary_chars=40).assemble(recent_limit=0, recall_query="沈青寻找仓库钥匙")
    assert "…仓库钥匙不是沈青拿走的。" in context.recall_block
    assert "灯会" not in context.recall_block
    hit = context.recall_report["selected"][0]
    assert summary[hit["source_start"]:hit["source_end"]] == "仓库钥匙不是沈青拿走的。"


def test_overlong_single_sentence_is_not_cut_into_misleading_evidence():
    rows = [{"chapter_id": "001", "summary": "仓库钥匙" + "没有交给沈青" * 20 + "。"}]
    selected, _ = select_history("仓库钥匙", rows, summary_chars=20)
    assert selected == []
    selected, _ = select_history(QUERY, SUMMARIES, summary_chars=0)
    assert selected == []


def test_feature_window_does_not_turn_a_partial_sentence_into_evidence():
    row = {"chapter_id": "001", "summary": "无关。" * 660 + "仓库钥匙不是" * 20 + "。"}
    selected, _ = select_history("仓库钥匙", [row], summary_chars=80)
    assert selected == []
