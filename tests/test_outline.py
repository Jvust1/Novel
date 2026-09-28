import pytest

from novel_ai.models import ChapterPlan, SceneBeat
from novel_ai.outline import (
    HierarchicalOutline,
    OutlineNode,
    build_hierarchical_outline,
    validate_outline,
)


def make_plan() -> ChapterPlan:
    return ChapterPlan(
        chapter_title="夜班电话",
        chapter_promise="主角必须在电话中作出第一次选择。",
        tension_curve="从异常发现升到被迫承诺。",
        scenes=[
            SceneBeat(
                scene_no=1,
                pov="林默",
                place="值班室",
                time="深夜",
                objective="确认来电者身份",
                opposition="对方拒绝直接回答",
                choice="继续追问",
                cost="暴露自己知道旧案",
                state_change="林默确认旧案重新出现",
                information_release=["来电与旧案有关"],
                foreshadowing=["未署名的录音"],
                environment_function="电话铃制造封闭空间压力",
                end_hook="对方说出一个已故者的名字",
            ),
        ],
        must_not_happen=["林默不能知道凶手身份"],
    )


def test_build_outline_preserves_plan_as_series_tree():
    outline = build_hierarchical_outline(
        "夜航者",
        "一个值班员被迫重新调查旧案。",
        [("第一卷：回声", [make_plan()])],
    )
    assert isinstance(outline, HierarchicalOutline)
    assert outline.root.level == "series"
    assert outline.root.children[0].level == "volume"
    arc = outline.root.children[0].children[0]
    assert arc.level == "arc"
    chapter = arc.children[0]
    assert chapter.level == "chapter"
    assert chapter.children[0].level == "scene"
    assert chapter.children[0].metadata["end_hook"] == "对方说出一个已故者的名字"
    assert len(outline.flatten()) == 5


def test_outline_ids_are_stable_for_same_input():
    first = build_hierarchical_outline("书", "设定", [("卷一", [make_plan()])])
    second = build_hierarchical_outline("书", "设定", [("卷一", [make_plan()])])
    assert [node.id for node in first.flatten()] == [node.id for node in second.flatten()]


def test_validation_rejects_skipped_levels_and_duplicate_ids():
    invalid = HierarchicalOutline(
        title="bad",
        root=OutlineNode(
            id="root",
            level="series",
            title="bad",
            children=[
                OutlineNode(id="chapter", level="chapter", title="跳级"),
            ],
        ),
    )
    with pytest.raises(ValueError, match="层级不连续"):
        validate_outline(invalid)

    duplicate = HierarchicalOutline(
        title="bad",
        root=OutlineNode(
            id="root",
            level="series",
            title="bad",
            children=[
                OutlineNode(
                    id="volume",
                    level="volume",
                    title="卷",
                    children=[
                        OutlineNode(
                            id="arc",
                            level="arc",
                            title="弧",
                            children=[
                                OutlineNode(id="same", level="chapter", title="一"),
                                OutlineNode(id="same", level="chapter", title="二"),
                            ],
                        )
                    ],
                )
            ],
        ),
    )
    with pytest.raises(ValueError, match="id 重复"):
        validate_outline(duplicate)


def test_outline_cli_runs_from_checkout(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).parents[1]
    input_path = tmp_path / "outline_input.json"
    output_path = tmp_path / "outline.json"
    input_path.write_text(
        json.dumps(
            {
                "title": "夜航者",
                "premise": "一个值班员被迫重新调查旧案。",
                "volumes": [
                    {
                        "title": "第一卷：回声",
                        "chapters": [make_plan().model_dump()],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_outline.py"),
            str(input_path),
            "--out",
            str(output_path),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )

    exported = json.loads(output_path.read_text(encoding="utf-8"))
    assert "Wrote" in result.stdout
    assert exported["root"]["level"] == "series"
    assert exported["root"]["children"][0]["children"][0]["children"][0]["level"] == "chapter"
