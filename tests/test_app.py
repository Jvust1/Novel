"""Headless execution tests for the Streamlit workbench via streamlit.testing."""

import json

import pytest
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def run_app(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    return at


def test_app_boots_without_exceptions(monkeypatch, tmp_path):
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception
    assert at.text_input(key="title").value == "MyNovel"  # 未保存时书名默认项目名


def test_app_reloads_persisted_project_state(monkeypatch, tmp_path):
    project_dir = tmp_path / "data" / "projects" / "MyNovel" / "memory"
    project_dir.mkdir(parents=True)
    (project_dir / "story_bible.json").write_text(
        json.dumps(
            {
                "title": "残脉",
                "genre": "玄幻",
                "tone": "冷峻",
                "premise": "灵气枯竭的大荒界。",
                "themes": ["生存"],
                "world_rules": ["灵石按滴计价"],
                "locked_facts": ["沈无咎体内封着祖龙残脉"],
                "forbidden_moves": ["不得轻易突破"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project_dir / "characters.json").write_text(
        json.dumps([{"name": "沈无咎", "identity": "杂役弟子"}], ensure_ascii=False),
        encoding="utf-8",
    )
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception
    assert at.text_input(key="title").value == "残脉"
    assert at.text_input(key="genre").value == "玄幻"
    assert at.text_area(key="rules_text").value == "灵石按滴计价"
    assert at.session_state["characters"][0]["name"] == "沈无咎"


def test_plan_confirmation_flow_gate(monkeypatch, tmp_path):
    """North Star: plan must be confirmable before drafting; ② stays gated without one."""
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception
    # 初始：没有待确认计划 → ② 禁用，计划编辑器不存在
    assert at.button(key="btn_draft").disabled is True
    assert not [w for w in at.text_area if w.key == "plan_editor"]

    # 注入一个待确认计划后：② 启用，计划编辑器出现且可编辑
    at.session_state["pending_plan_json"] = json.dumps({"chapter_title": "测试章", "scenes": []})
    at.session_state["plan_new"] = True
    at.run()
    assert at.button(key="btn_draft").disabled is False
    assert at.text_area(key="plan_editor").value == at.session_state["pending_plan_json"]


def test_diverse_recall_is_explicit_and_off_by_default(monkeypatch, tmp_path):
    at = run_app(monkeypatch, tmp_path)
    assert at.checkbox(key="diverse_recall").value is False
    at.checkbox(key="diverse_recall").check().run()
    assert not at.exception
    assert at.checkbox(key="diverse_recall").value is True


@pytest.mark.parametrize("confirmed_plan", [True, False])
def test_workbench_carries_recalled_evidence_through_confirmed_plan_and_repair(monkeypatch, tmp_path, confirmed_plan):
    from novel_ai.provider import OpenAICompatibleProvider
    from novel_ai.storage import ProjectStore

    calls = []
    def chat(self, messages, **kwargs):
        system = messages[0]["content"]
        calls.append(messages)
        if "章节策划" in system:
            return json.dumps({"chapter_title": "试读", "scenes": []})
        if "严苛的网络小说章节编辑" in system:
            return json.dumps({"verdict": "revise", "issues": []})
        return "沈青收好仓库钥匙。林澄翻开账本。"
    monkeypatch.setattr(OpenAICompatibleProvider, "chat", chat)
    store = ProjectStore(tmp_path / "data")
    for i in range(6):
        store.save_extraction("MyNovel", {"chapter_id": f"{i:03}", "summary": "仓库钥匙藏在青瓷碗底。" if i == 0 else "村民去了集市。"})
    at = run_app(monkeypatch, tmp_path)
    for item in at.text_input:
        if item.label == "Base URL":
            item.set_value("http://never-called.invalid")
        if item.label == "Model":
            item.set_value("fake")
    for item in at.text_area:
        if item.label == "本章章纲 / 目标":
            item.set_value("沈青寻找仓库钥匙。")
    at.checkbox(key="diverse_recall").check()
    at.radio[0].set_value("精修")
    if confirmed_plan:
        at.button(key="btn_plan").click().run()
        assert not at.exception
        assert "仓库钥匙藏在青瓷碗底" in at.session_state["pending_plan_meta"]["extra"]
        at.button(key="btn_draft").click().run()
    else:
        at.button(key="btn_oneshot").click().run()
    assert not at.exception
    assert len(calls) == 5
    assert all("仓库钥匙藏在青瓷碗底" in messages[-1]["content"] for messages in calls)
    assert at.session_state["last_result"].review_after_repair is not None


def test_memory_writeback_persists_character_knowledge_across_fresh_sessions(monkeypatch, tmp_path):
    from novel_ai.engine import ChapterResult
    from novel_ai.models import ChapterPlan, ChapterReview
    from novel_ai.provider import OpenAICompatibleProvider
    from novel_ai.storage import ProjectStore
    from novel_ai.story_dna import story_dna_from_plan

    original = [
        {"name": "沈青", "does_not_know": ["账本由林澄保管"], "knows": []},
        {"name": "林舟", "locked": True, "does_not_know": ["仓库密码"], "knows": []},
    ]
    store = ProjectStore(tmp_path / "data")
    store.write_json("MyNovel", "memory/characters.json", original)
    def chat(self, messages, **kwargs):
        assert "连续性记录员" in messages[0]["content"]
        return json.dumps({
            "chapter_id": "007", "summary": "沈青向林澄借账本核对。",
            "character_updates": [
                {"name": "沈青", "knowledge_gained": ["账本由林澄保管"]},
                {"name": "林舟", "knowledge_gained": ["仓库密码"]},
            ],
        }, ensure_ascii=False)
    monkeypatch.setattr(OpenAICompatibleProvider, "chat", chat)
    at = run_app(monkeypatch, tmp_path)
    plan = ChapterPlan(chapter_title="核账")
    at.session_state["last_result"] = ChapterResult(
        plan=plan, draft="沈青向林澄借账本核对。", review=ChapterReview(verdict="pass"),
        ai_flavor={}, story_dna=story_dna_from_plan(plan).to_dict(),
    )
    from novel_ai.author_workflow import write_author_chapter, save_chapter_plan
    import hashlib
    text = "沈青向林澄借账本核对。"
    write_author_chapter(store, "MyNovel", "007", text)
    save_chapter_plan(store, "MyNovel", "007", plan, text)
    at.session_state["last_result_meta"] = {"project": "MyNovel", "chapter_id": "007",
        "text_sha256": hashlib.sha256((text + "\n").encode()).hexdigest()}
    at.run()
    for item in at.text_input:
        if item.label == "Base URL":
            item.set_value("http://never-called.invalid")
        if item.label == "Model":
            item.set_value("fake")
        if item.label == "章节编号 / 名称":
            item.set_value("007")
    at.run()
    next(button for button in at.button if button.label == "提取本章记忆候选 不回写").click().run()
    assert not at.exception
    assert store.read_json("MyNovel", "memory/characters.json") == original
    assert at.session_state["last_extraction"] is None
    next(x for x in at.checkbox if x.label == "我接受这一版正文作为记忆来源").check().run()
    next(x for x in at.checkbox if x.label == "我已查看并接受这份记忆变更").check().run()
    at.button(key="btn_memory_apply").click().run()
    assert not at.exception
    saved = store.read_json("MyNovel", "memory/characters.json")
    assert saved[0]["knows"] == ["账本由林澄保管"]
    assert saved[0]["does_not_know"] == []
    assert saved[1]["knows"] == []
    assert saved[1]["does_not_know"] == ["仓库密码"]
    restarted = run_app(monkeypatch, tmp_path)
    assert not restarted.exception
    assert restarted.session_state["characters"] == saved
    assert store.all_chapter_summaries("MyNovel")[-1]["chapter_id"] == "007"


@pytest.mark.parametrize("repair_introduces_drift", [True, False])
def test_confirmed_plan_rereview_detects_repaired_speaker_voice_drift(monkeypatch, tmp_path, repair_introduces_drift):
    from novel_ai.dialogue_attribution import ATTRIBUTION_VERSION
    from novel_ai.provider import OpenAICompatibleProvider
    from novel_ai.storage import ProjectStore

    draft = ('林舟明问：“为什么你现在才来，仓库早已经封门了？”\n'
             '林舟明问：“你昨天走过城门的时候，难道没有听见钟声吗？”')
    revised = draft.replace("林舟明", "林舟")
    if not repair_introduces_drift:
        draft, revised = revised, draft
    reviews = []
    def chat(self, messages, **kwargs):
        system = messages[0]["content"]
        if "严苛的网络小说章节编辑" in system:
            reviews.append(messages)
            return json.dumps({"verdict": "revise" if len(reviews) == 1 else "pass", "issues": []})
        return revised if "局部修订编辑" in system else draft
    monkeypatch.setattr(OpenAICompatibleProvider, "chat", chat)
    store = ProjectStore(tmp_path / "data")
    store.write_json("MyNovel", "memory/characters.json", [{"name": "林舟"}, {"name": "林舟明"}])
    store.save_voice_dna("MyNovel", "000", {"林舟": {
        "attribution_version": ATTRIBUTION_VERSION, "line_count": 12,
        "avg_line_chars": 3, "question_ratio": 0, "short_line_ratio": 1,
        "exclamation_ratio": 1, "ellipsis_ratio": 1,
    }})
    at = run_app(monkeypatch, tmp_path)
    at.session_state["pending_plan_json"] = json.dumps({"chapter_title": "问话", "scenes": []})
    at.session_state["plan_new"] = True
    at.run()
    for item in at.text_input:
        if item.label == "Base URL":
            item.set_value("http://never-called.invalid")
        if item.label == "Model":
            item.set_value("fake")
    at.radio[0].set_value("精修")
    at.button(key="btn_draft").click().run()
    assert not at.exception
    result = at.session_state["last_result"]
    assert result.final_text == revised
    if repair_introduces_drift:
        assert result.voice_dna_report["alerts"] == []
        assert result.review_after_repair.verdict == "revise"
        assert any(issue.category == "人物口吻漂移" for issue in result.review_after_repair.issues)
        assert result.voice_dna_report["revised_alerts"][0]["character"] == "林舟"
        assert any("人物口吻 DNA 漂移" in warning.value for warning in at.warning)
    else:
        assert result.voice_dna_report["alerts"]
        assert result.voice_dna_report["revised_alerts"] == []
        assert result.review_after_repair.verdict == "pass"
        assert not any("人物口吻 DNA 漂移" in warning.value for warning in at.warning)
    assert len(reviews) == 2


@pytest.mark.parametrize("mode", ["标准审校", "精修"])
def test_confirmed_plan_reference_overlap_enters_review_and_rereview(monkeypatch, tmp_path, mode):
    from novel_ai.provider import OpenAICompatibleProvider
    from novel_ai.style_engine import build_reference_signature

    original_synthetic_text = '柜门里藏着一本蓝色账册，沈青把纸页一张张摊开，林澄在窗边逐项核对那些模糊的日期。'
    calls = []
    def chat(self, messages, **kwargs):
        calls.append(messages)
        if "严苛的网络小说章节编辑" in messages[0]["content"]:
            return json.dumps({"verdict": "pass", "issues": []})
        return original_synthetic_text
    monkeypatch.setattr(OpenAICompatibleProvider, "chat", chat)
    at = run_app(monkeypatch, tmp_path)
    at.session_state["pending_plan_json"] = json.dumps({"chapter_title": "核账", "scenes": []})
    at.session_state["plan_new"] = True
    at.session_state["reference_hashes"] = build_reference_signature(original_synthetic_text)
    at.run()
    for item in at.text_input:
        if item.label == "Base URL":
            item.set_value("http://never-called.invalid")
        if item.label == "Model":
            item.set_value("fake")
    at.radio[0].set_value(mode)
    at.button(key="btn_draft").click().run()
    assert not at.exception
    result = at.session_state["last_result"]
    assert result.similarity_report is not None
    assert result.review.verdict == "revise"
    assert any(issue.category == "参考片段重合" for issue in result.review.issues)
    if mode == "精修":
        assert result.review_after_repair.verdict == "revise"
        assert any(issue.category == "参考片段重合" for issue in result.review_after_repair.issues)
        assert len(calls) == 4  # One repair only, even when the overlap persists.
    else:
        assert result.revised is None
        assert len(calls) == 2


def test_project_switch_isolates_plan_characters_and_restores_unsaved_goal(monkeypatch, tmp_path):
    from novel_ai.storage import ProjectStore
    store = ProjectStore(tmp_path / "data")
    store.write_json("OtherBook", "memory/characters.json", [{"name": "OnlyB"}])
    at = run_app(monkeypatch, tmp_path)
    at.session_state["characters"] = [{"name": "OnlyA"}]
    at.session_state["pending_plan_json"] = json.dumps({"chapter_title": "A计划", "scenes": []})
    at.session_state["pending_plan_meta"] = {"extra": "OnlyA的历史"}
    at.session_state["plan_new"] = True
    at.text_area(key="chapter_goal").set_value("A的未保存章纲").run()
    at.checkbox(key="diverse_recall").check().run()
    at.text_input(key="project_name").set_value("OtherBook").run()
    assert not at.exception
    assert at.session_state["characters"] == [{"name": "OnlyB"}]
    assert at.session_state["pending_plan_json"] == ""
    assert at.session_state["last_result"] is None
    assert at.text_area(key="chapter_goal").value == ""
    assert at.checkbox(key="diverse_recall").value is False
    assert at.button(key="btn_draft").disabled
    at.text_input(key="project_name").set_value("MyNovel").run()
    assert not at.exception
    assert at.session_state["characters"] == [{"name": "OnlyA"}]
    assert at.session_state["pending_plan_meta"] == {"extra": "OnlyA的历史"}
    assert at.text_area(key="chapter_goal").value == "A的未保存章纲"
    assert at.checkbox(key="diverse_recall").value is True
    assert not at.button(key="btn_draft").disabled
    assert store.read_json("MyNovel", "memory/characters.json") is None
    assert store.read_json("OtherBook", "memory/characters.json") == [{"name": "OnlyB"}]


def test_failed_project_switch_restores_widget_drafts_when_returning(monkeypatch, tmp_path):
    from novel_ai.storage import ProjectStore
    store = ProjectStore(tmp_path / "data")
    broken = store.project_dir("Broken") / "memory/story_bible.json"
    broken.write_text("{invalid JSON", encoding="utf-8")
    at = run_app(monkeypatch, tmp_path)
    at.session_state["characters"] = [{"name": "UnsavedA"}]
    at.text_area(key="chapter_goal").set_value("不能丢失的未保存章纲").run()
    at.text_input(key="project_name").set_value("Broken").run()
    assert at.exception
    at.text_input(key="project_name").set_value("MyNovel").run()
    assert not at.exception
    assert at.session_state["characters"] == [{"name": "UnsavedA"}]
    assert at.text_area(key="chapter_goal").value == "不能丢失的未保存章纲"


def test_new_character_form_draft_stays_with_its_project(monkeypatch, tmp_path):
    at = run_app(monkeypatch, tmp_path)
    at.text_input(key="new_char_name").set_value("尚未添加的甲角色")
    at.text_input(key="new_char_secret").set_value("只属于甲书的虚构秘密").run()
    at.text_input(key="project_name").set_value("OtherBook").run()
    assert not at.exception
    assert at.text_input(key="new_char_name").value == ""
    assert at.text_input(key="new_char_secret").value == ""
    at.text_input(key="project_name").set_value("MyNovel").run()
    assert not at.exception
    assert at.text_input(key="new_char_name").value == "尚未添加的甲角色"
    assert at.text_input(key="new_char_secret").value == "只属于甲书的虚构秘密"


def test_blank_project_roundtrip_keeps_unsaved_widget_goal(monkeypatch, tmp_path):
    at = run_app(monkeypatch, tmp_path)
    at.text_input(key="project_name").set_value("").run()
    at.text_area(key="chapter_goal").set_value("空白名称项目的未保存章纲").run()
    at.text_input(key="project_name").set_value("OtherBook").run()
    at.text_input(key="project_name").set_value("").run()
    assert not at.exception
    assert at.text_area(key="chapter_goal").value == "空白名称项目的未保存章纲"


def test_distinct_locked_facts_survive_load_save_restart_and_plan_prompt(monkeypatch, tmp_path):
    from novel_ai.provider import OpenAICompatibleProvider
    from novel_ai.storage import ProjectStore
    store = ProjectStore(tmp_path / "data")
    store.write_json("MyNovel", "memory/story_bible.json", {
        "title": "试验书", "world_rules": ["城门每夜关闭"],
        "locked_facts": ["钥匙一直由沈青保管"],
    })
    prompts = []
    def chat(self, messages, **kwargs):
        assert "章节策划" in messages[0]["content"]
        prompts.append(messages[-1]["content"])
        return json.dumps({"chapter_title": "核账", "scenes": []})
    monkeypatch.setattr(OpenAICompatibleProvider, "chat", chat)
    at = run_app(monkeypatch, tmp_path)
    assert at.text_area(key="rules_text").value == "城门每夜关闭"
    assert at.text_area(key="locked_text").value == "钥匙一直由沈青保管"
    at.text_area(key="locked_text").set_value("钥匙一直由沈青保管\n账本已经交给林澄").run()
    next(button for button in at.button if button.label == "保存故事设定到本地").click().run()
    assert not at.exception
    saved = store.read_json("MyNovel", "memory/story_bible.json")
    assert saved["world_rules"] == ["城门每夜关闭"]
    assert saved["locked_facts"] == ["钥匙一直由沈青保管", "账本已经交给林澄"]
    restarted = run_app(monkeypatch, tmp_path)
    assert restarted.text_area(key="locked_text").value == "钥匙一直由沈青保管\n账本已经交给林澄"
    for item in restarted.text_input:
        if item.label == "Base URL":
            item.set_value("http://never-called.invalid")
        if item.label == "Model":
            item.set_value("fake")
    restarted.button(key="btn_plan").click().run()
    assert not restarted.exception
    assert len(prompts) == 1
    assert '"world_rules": [\n    "城门每夜关闭"' in prompts[0]
    assert '"locked_facts": [\n    "钥匙一直由沈青保管",\n    "账本已经交给林澄"' in prompts[0]


def test_locked_fact_editor_is_project_scoped(monkeypatch, tmp_path):
    from novel_ai.storage import ProjectStore
    store = ProjectStore(tmp_path / "data")
    store.write_json("OtherBook", "memory/story_bible.json", {"locked_facts": ["乙书事实"]})
    at = run_app(monkeypatch, tmp_path)
    at.text_area(key="locked_text").set_value("甲书未保存事实").run()
    at.text_input(key="project_name").set_value("OtherBook").run()
    assert at.text_area(key="locked_text").value == "乙书事实"
    at.text_input(key="project_name").set_value("MyNovel").run()
    assert not at.exception
    assert at.text_area(key="locked_text").value == "甲书未保存事实"
