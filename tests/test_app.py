"""Headless execution tests for the Streamlit workbench via streamlit.testing."""

import json
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
