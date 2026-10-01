"""Real Streamlit reruns around a provider-mocked, synthetic author workflow."""
import csv
import io
import json
import zipfile
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from novel_ai.author_workflow import load_author_corpus
from novel_ai.market_eval import market_scoring_csv
from novel_ai.provider import OpenAICompatibleProvider
from novel_ai.storage import ProjectStore

APP = Path(__file__).resolve().parents[1] / "app.py"
MARKDOWN = """# 归航\n全书承诺：守住真实航图\n## 第一卷\n卷级限制：风暴前必须返航\n### 灯塔线\n情节线：每次选择都有代价\n#### 初次登塔\n第一章找回旧灯芯\n##### 登塔\n林澄想进入灯室\n#### 遗失航图\n第二章找回航图\n##### 查仓\n沈青查仓\n#### 返航\n第三章承担返航代价\n##### 驾船\n林澄选择回港\n"""


def run_app(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    return AppTest.from_file(str(APP), default_timeout=30).run()


def button(at, label):
    return next(item for item in at.button if item.label == label)


def import_outline(at):
    at.text_area(key="hierarchy_markdown").set_value(MARKDOWN)
    at.button(key="btn_parse_hierarchy").click().run()
    assert not at.exception
    at.button(key="btn_save_hierarchy").click().run()
    assert not at.exception
    return at


def configure_provider(at):
    next(item for item in at.text_input if item.label == "Base URL").set_value("http://never-called.invalid")
    next(item for item in at.text_input if item.label == "Model").set_value("synthetic-provider")
    at.radio[0].set_value("快速草稿")


def provider_stub(monkeypatch):
    calls = []
    def chat(self, messages, **kwargs):
        calls.append(messages)
        if "章节策划" in messages[0]["content"]:
            return json.dumps({
                "chapter_title": "测试标题", "chapter_promise": "作者确认的测试目标", "scenes": [{
                    "scene_no": 1, "pov": "林澄", "objective": "找灯芯", "opposition": "门被封住",
                    "choice": "借钥匙", "cost": "欠下承诺", "state_change": "拿到灯芯",
                }],
            }, ensure_ascii=False)
        return "林澄借来了钥匙。她把灯芯放进空盒，答应天亮前还回去。"
    monkeypatch.setattr(OpenAICompatibleProvider, "chat", chat)
    return calls


def fill_release(at, chapter_ids):
    at.text_area(key="release_chapter_order").set_value("\n".join(chapter_ids))
    for key, value in {
        "release_title": "归航", "release_genre": "原创悬疑", "release_audience": "成年悬疑读者",
        "release_hook": "三个返航者必须交还一份航图",
    }.items():
        at.text_input(key=key).set_value(value)
    at.text_area(key="release_blurb").set_value("在风暴前，他们重新选择了自己的归途。")
    at.run()
    assert not at.exception


def filled_scores(corpus):
    rows = list(csv.DictReader(io.StringIO(market_scoring_csv(corpus))))
    for row in rows:
        row.update(reviewer_id="synthetic-reviewer", score="4", note="测试记录，不是真人质量结论")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def test_outline_to_three_saved_chapters_to_review_and_release_restart(monkeypatch, tmp_path):
    calls = provider_stub(monkeypatch)
    at = import_outline(run_app(monkeypatch, tmp_path))
    chapter_nodes = [node for node in at.session_state.hierarchy_data["root"]["children"][0]["children"][0]["children"]]
    ids = ["001", "002", "003"]
    for node, chapter_id in zip(chapter_nodes, ids):
        at.selectbox(key="hierarchy_selected").set_value(node["id"]).run()
        at.text_input(key="hierarchy_target_id").set_value(chapter_id)
        at.button(key="btn_load_hierarchy").click().run()
        assert not at.exception
        assert at.text_input(key="chapter_id").value == chapter_id
        assert at.session_state.last_result is None
        configure_provider(at)
        at.button(key="btn_plan").click().run()
        assert not at.exception
        assert "风暴前必须返航" in calls[-1][-1]["content"]
        assert node["promise"] in calls[-1][-1]["content"]
        assert node["children"][0]["promise"] in calls[-1][-1]["content"]
        at.button(key="btn_draft").click().run()
        assert not at.exception
        assert at.session_state.last_result_meta["project"] == "MyNovel"
        assert at.session_state.last_result_meta["chapter_id"] == chapter_id
        assert len(at.session_state.last_result_meta["text_sha256"]) == 64
    assert len(calls) == 6
    store = ProjectStore(tmp_path / "data")
    assert len(store.all_chapter_texts("MyNovel")) == 3
    assert len(list((store.project_dir("MyNovel") / "memory/chapter_plans").glob("*.json"))) == 3
    fill_release(at, ids)
    at.button(key="btn_save_release_bundle").click().run()
    assert not at.exception
    exports = list((store.project_dir("MyNovel") / "exports").glob("*.zip"))
    assert len(exports) == 1
    with zipfile.ZipFile(exports[0]) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["human_review_status"] == "awaiting_human_review"
        assert [row["chapter_id"] for row in manifest["chapters"]] == ids
        assert bundle.read("chapters/001.md").decode() == store.all_chapter_texts("MyNovel")[0][1]
    corpus = load_author_corpus(store, "MyNovel", ids, "opening_3", audience="成年悬疑读者", genre="原创悬疑")
    at.text_area(key="release_scores_text").set_value(filled_scores(corpus)).run()
    assert not at.exception
    at.button(key="btn_save_release_draft").click().run()
    at.button(key="btn_save_release_bundle").click().run()
    assert not at.exception
    assert len(list((store.project_dir("MyNovel") / "exports").glob("*.zip"))) == 2
    at.button(key="btn_save_release_bundle").click().run()
    assert len(list((store.project_dir("MyNovel") / "exports").glob("*.zip"))) == 2
    restarted = run_app(monkeypatch, tmp_path)
    assert not restarted.exception
    assert restarted.text_area(key="release_chapter_order").value == "001\n002\n003"
    assert restarted.text_input(key="release_audience").value == "成年悬疑读者"
    assert restarted.text_area(key="release_scores_text").value
    assert restarted.session_state.last_result is None
    assert restarted.selectbox(key="hierarchy_selected").value == chapter_nodes[0]["id"]
    # No provider calls while rendering, scoring, saving, switching or restarting.
    assert len(calls) == 6
    store.write_chapter("MyNovel", "001", "修订后的不同正文。")
    restarted.run()
    assert not restarted.exception
    assert any("评分不能用于当前候选包" in item.value for item in restarted.error)
    assert not any(item.key == "btn_save_release_bundle" for item in restarted.button)
    assert len(list((store.project_dir("MyNovel") / "exports").glob("*.zip"))) == 2


def test_incomplete_outline_plan_and_changed_binding_block_before_provider(monkeypatch, tmp_path):
    calls = provider_stub(monkeypatch)
    at = import_outline(run_app(monkeypatch, tmp_path))
    at.text_input(key="hierarchy_target_id").set_value("001")
    at.button(key="btn_load_hierarchy").click().run()
    configure_provider(at)
    at.button(key="btn_draft").click().run()
    assert any("补全场景计划" in str(item.message) for item in at.exception)
    assert calls == []
    at.text_input(key="chapter_id").set_value("other")
    at.button(key="btn_draft").click().run()
    assert any("另一章" in str(item.message) for item in at.exception)
    assert calls == []
    at.button(key="btn_clear_plan").click().run()
    assert not at.exception
    assert at.button(key="btn_draft").disabled


def test_saved_outline_edit_invalidates_plan_and_memory_is_bound(monkeypatch, tmp_path):
    calls = provider_stub(monkeypatch)
    at = import_outline(run_app(monkeypatch, tmp_path))
    at.text_input(key="hierarchy_target_id").set_value("001")
    at.button(key="btn_load_hierarchy").click().run()
    configure_provider(at)
    at.button(key="btn_plan").click().run()
    at.button(key="btn_draft").click().run()
    assert not at.exception
    at.text_input(key="chapter_id").set_value("002").run()
    assert button(at, "抽取本章记忆并回写").disabled
    assert any("另一章" in warning.value for warning in at.warning)
    data = at.session_state.hierarchy_data.copy()
    data["premise"] = "修改后的设定"
    at.text_area(key="hierarchy_editor").set_value(json.dumps(data, ensure_ascii=False))
    at.button(key="btn_save_hierarchy").click().run()
    at.text_input(key="chapter_id").set_value("001").run()
    at.checkbox(key="allow_chapter_overwrite").check()
    at.button(key="btn_draft").click().run()
    assert any("大纲已变化" in str(item.message) for item in at.exception)
    assert len(calls) == 2


def test_release_workbench_state_is_project_scoped_including_failed_load(monkeypatch, tmp_path):
    at = import_outline(run_app(monkeypatch, tmp_path))
    at.text_input(key="release_hook").set_value("A 未保存看点")
    at.text_area(key="release_scores_text").set_value("A 未保存评分")
    at.text_area(key="hierarchy_markdown").set_value("A 未保存大纲")
    at.run()
    at.text_input(key="project_name").set_value("B").run()
    assert not at.exception
    assert at.text_input(key="release_hook").value == ""
    assert at.text_area(key="release_scores_text").value == ""
    assert not at.session_state.hierarchy_data
    at.text_input(key="project_name").set_value("MyNovel").run()
    assert at.text_input(key="release_hook").value == "A 未保存看点"
    assert at.text_area(key="release_scores_text").value == "A 未保存评分"
    assert at.text_area(key="hierarchy_markdown").value == "A 未保存大纲"
    store = ProjectStore(tmp_path / "data")
    (store.project_dir("Broken") / "memory/release_workspace.json").write_text("{bad", encoding="utf-8")
    at.text_input(key="project_name").set_value("Broken").run()
    assert at.exception
    at.text_input(key="project_name").set_value("MyNovel").run()
    assert not at.exception
    assert at.text_input(key="release_hook").value == "A 未保存看点"
    assert at.text_area(key="release_scores_text").value == "A 未保存评分"


def test_overwrite_and_unsafe_id_do_not_call_model(monkeypatch, tmp_path):
    calls = provider_stub(monkeypatch)
    store = ProjectStore(tmp_path / "data")
    path = store.write_chapter("MyNovel", "001", "已有正文")
    at = run_app(monkeypatch, tmp_path)
    configure_provider(at)
    at.button(key="btn_oneshot").click().run()
    assert calls == []
    assert path.read_text() == "已有正文\n"
    assert any("已有正文" in str(item.message) for item in at.exception)
    at.text_input(key="chapter_id").set_value("../001")
    at.button(key="btn_oneshot").click().run()
    assert calls == []
    assert at.exception


def test_unrelated_non_utf8_manuscript_does_not_break_workbench(monkeypatch, tmp_path):
    store = ProjectStore(tmp_path / "data")
    (store.project_dir("MyNovel") / "chapters/unrelated.md").write_bytes(b"\xff\xfe\x80")
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception
    assert at.text_input(key="title").value == "MyNovel"


def test_overwrite_permission_is_reset_when_switching_chapter(monkeypatch, tmp_path):
    calls = provider_stub(monkeypatch)
    store = ProjectStore(tmp_path / "data")
    for chapter_id in ("001", "002"):
        store.write_chapter("MyNovel", chapter_id, "原稿" + chapter_id)
    at = run_app(monkeypatch, tmp_path)
    at.checkbox(key="allow_chapter_overwrite").check().run()
    assert at.checkbox(key="allow_chapter_overwrite").value
    at.text_input(key="chapter_id").set_value("002").run()
    assert not at.checkbox(key="allow_chapter_overwrite").value
    configure_provider(at)
    at.button(key="btn_oneshot").click().run()
    assert at.exception
    assert calls == []
    assert (store.project_dir("MyNovel") / "chapters/002.md").read_text() == "原稿002\n"


def test_plan_save_failure_cannot_rebind_new_text_to_previous_result(monkeypatch, tmp_path):
    import novel_ai.author_workflow as workflow
    provider_stub(monkeypatch)
    at = run_app(monkeypatch, tmp_path)
    configure_provider(at)
    at.button(key="btn_oneshot").click().run()
    assert not at.exception
    previous_result = at.session_state.last_result
    previous_meta = dict(at.session_state.last_result_meta)
    def fail(*args, **kwargs):
        raise OSError("synthetic interrupted plan write")
    monkeypatch.setattr(workflow, "save_chapter_plan", fail)
    at.text_input(key="chapter_id").set_value("002")
    at.button(key="btn_oneshot").click().run()
    assert at.exception
    assert at.session_state.last_result == previous_result
    assert at.session_state.last_result_meta == previous_meta
    assert button(at, "抽取本章记忆并回写").disabled
    at.text_input(key="chapter_id").set_value("001").run()
    assert not at.exception
    assert at.session_state.last_result_meta["chapter_id"] == "001"
    assert not button(at, "抽取本章记忆并回写").disabled


def test_externally_changed_saved_revision_blocks_old_memory(monkeypatch, tmp_path):
    calls = provider_stub(monkeypatch)
    at = run_app(monkeypatch, tmp_path)
    configure_provider(at)
    at.button(key="btn_oneshot").click().run()
    assert not at.exception
    ProjectStore(tmp_path / "data").write_chapter("MyNovel", "001", "不同的新版本正文")
    at.run()
    assert not at.exception
    assert button(at, "抽取本章记忆并回写").disabled
    assert any("正文发生变化" in item.value for item in at.warning)
    assert len(calls) == 2


@pytest.mark.parametrize("chapter_id", ["-001", "001-", "../001"])
def test_aliasing_chapter_ids_cannot_overwrite_before_provider(monkeypatch, tmp_path, chapter_id):
    calls = provider_stub(monkeypatch)
    store = ProjectStore(tmp_path / "data")
    saved = store.write_chapter("MyNovel", "001", "原稿")
    at = run_app(monkeypatch, tmp_path)
    configure_provider(at)
    at.text_input(key="chapter_id").set_value(chapter_id)
    at.button(key="btn_oneshot").click().run()
    assert at.exception
    assert calls == []
    assert saved.read_text() == "原稿\n"


@pytest.mark.parametrize("bad", [{"release_hook": []}, {"release_stage": "unknown"}, ["not-an-object"]])
def test_invalid_saved_release_types_do_not_commit_target_project(monkeypatch, tmp_path, bad):
    store = ProjectStore(tmp_path / "data")
    store.write_json("Broken", "memory/release_workspace.json", bad)
    original = (store.project_dir("Broken") / "memory/release_workspace.json").read_bytes()
    at = run_app(monkeypatch, tmp_path)
    at.text_input(key="release_hook").set_value("未保存看点").run()
    at.text_input(key="project_name").set_value("Broken").run()
    assert at.exception
    assert at.session_state.seeded_project == "MyNovel"
    at.text_input(key="project_name").set_value("MyNovel").run()
    assert not at.exception
    assert at.text_input(key="release_hook").value == "未保存看点"
    assert (store.project_dir("Broken") / "memory/release_workspace.json").read_bytes() == original


def test_unreadable_unrelated_chapter_cannot_hide_release_tab_with_result(monkeypatch, tmp_path):
    provider_stub(monkeypatch)
    at = run_app(monkeypatch, tmp_path)
    configure_provider(at)
    at.button(key="btn_oneshot").click().run()
    assert not at.exception
    store = ProjectStore(tmp_path / "data")
    (store.project_dir("MyNovel") / "chapters/unrelated.md").write_bytes(b"\xff\xfe\x80")
    at.run()
    assert not at.exception
    assert any("综合质量快照未完成" in item.value for item in at.warning)
    assert at.text_input(key="release_hook") is not None


def test_editable_seed_plan_survives_complete_plan_request(monkeypatch, tmp_path):
    calls = provider_stub(monkeypatch)
    at = import_outline(run_app(monkeypatch, tmp_path))
    at.text_input(key="hierarchy_target_id").set_value("001")
    at.button(key="btn_load_hierarchy").click().run()
    seed = json.loads(at.text_area(key="plan_editor").value)
    seed["scenes"][0]["choice"] = "作者独有选择：把钥匙交给船主"
    at.text_area(key="plan_editor").set_value(json.dumps(seed, ensure_ascii=False))
    configure_provider(at)
    at.button(key="btn_plan").click().run()
    assert not at.exception
    assert len(calls) == 1
    assert "作者独有选择：把钥匙交给船主" in calls[0][-1]["content"]
    assert "林澄想进入灯室" in calls[0][-1]["content"]
