"""Checks that the opening skill reaches both the GPT workflow and live prompt builders.

These contracts do not measure prose immersion or prove model compliance.
"""
from pathlib import Path

from novel_ai.models import StoryBible
from novel_ai.prompts import draft_messages, plan_messages, repair_messages, review_messages

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/novel-opening-immersion/SKILL.md"
PROMPTS = ROOT / "docs/prompts/natural-fiction"


def test_opening_guidance_flows_into_runtime_messages_without_schema_changes():
    bible = StoryBible(genre="都市/日常")
    plan = plan_messages(bible, "既定大纲", "第一章：已有小目标", [], [])
    assert "若本次是新书开篇" in plan[0]["content"]
    assert "具体阻力" in plan[0]["content"]
    assert '"scenes"' in plan[1]["content"]
    assert '"information_release"' in plan[1]["content"]

    draft = draft_messages(bible, {"scenes": []}, [], [], None, 1200, user_notes="只写已确认事实")
    assert "章首尽快建立视角人物" in draft[0]["content"]
    assert "不按五感填表" in draft[0]["content"]
    assert "只写已确认事实" in draft[1]["content"]
    assert "直接输出小说正文" in draft[1]["content"]

    review = review_messages(bible, {"scenes": []}, [], "合成示例草稿")
    assert "开头能否让读者" in review[1]["content"]
    assert "原句" in review[1]["content"]
    for expected in ('"verdict"', '"issues"', '"continuity_updates"'):
        assert expected in review[1]["content"]


def test_opening_skill_is_explicitly_wired_into_gpt_stage_prompts():
    assert SKILL.is_file()
    skill = SKILL.read_text(encoding="utf-8")
    for marker in ["name: novel-opening-immersion", "视角", "当下目标", "代价", "作者确认", "不按", "MIT"]:
        assert marker in skill
    for filename in ("01-writing-before.md", "02-editorial-review.md", "README.md"):
        assert "../../../skills/novel-opening-immersion/SKILL.md" in (PROMPTS / filename).read_text(encoding="utf-8")
    assert "../skills/novel-opening-immersion/SKILL.md" in (ROOT / "docs/GPT_WRITING_ENTRY.md").read_text(encoding="utf-8")


def test_immersion_repair_stage_keeps_existing_contract_and_limits_scope():
    sentinel = "合成章节开头。\n\n下文没有变化。"
    issue = {"issues": [{"category": "开篇代入感", "excerpt": "合成章节开头。", "reason": "主角的当下阻力不清楚", "suggestion": "仅调整已知信息顺序"}]}
    messages = repair_messages(sentinel, issue, None, extra_context="既有章节来源证据")
    assert "若问题涉及首场代入感" in messages[0]["content"]
    assert "不添加未确认的事故" in messages[0]["content"]
    assert "留待作者重新确认章计划" in messages[0]["content"]
    assert sentinel in messages[1]["content"]
    assert "既有章节来源证据" in messages[1]["content"]
    assert "输出修订后的完整正文" in messages[1]["content"]
