from novel_ai.memory import apply_extraction
from novel_ai.models import (
    Character,
    CharacterMemoryUpdate,
    ForeshadowItem,
    MemoryExtraction,
    TimelineEvent,
)


def make_extraction() -> MemoryExtraction:
    return MemoryExtraction(
        chapter_id="003",
        chapter_title="夜访",
        summary="林舟潜入档案室，发现父亲的名字被人为抹去，被巡查逼入死角后翻窗逃离。",
        new_facts=["档案室里关于林父的记录被人为抹去", "巡查队夜里十点换岗"],
        character_updates=[
            CharacterMemoryUpdate(
                name="林舟",
                goal_change="查清是谁抹掉了父亲的档案",
                state_changes={"位置": "城南旧仓库", "伤势": "左臂划伤"},
                relationship_changes={"苏晚": "从怀疑转为初步合作"},
                knowledge_gained=["档案被抹去的痕迹是三个月内留下的"],
                misconceptions_cleared=["巡查队只在白天巡逻"],
                resources_gained=["档案室备用钥匙"],
                recent_change="正式与苏晚结盟，开始反查档案室",
            ),
            CharacterMemoryUpdate(
                name="路人甲",
                recent_change="不存在的角色",
            ),
        ],
        timeline_events=[
            TimelineEvent(chapter_id="003", description="林舟夜访档案室", time_hint="当夜"),
        ],
        foreshadowing=[
            ForeshadowItem(id="archive-gap", description="档案被抹去的三个月空窗", status="planted", chapter_id="003")
        ],
        open_threads=["是谁抹掉了档案"],
    )


def test_knowledge_gained_updates_boundaries():
    lin = Character(name="林舟", does_not_know=["档案被抹去的痕迹是三个月内留下的"])
    chars, state = apply_extraction([lin], {}, make_extraction())
    updated = chars[0]
    assert "档案被抹去的痕迹是三个月内留下的" in updated.knows
    assert "档案被抹去的痕迹是三个月内留下的" not in updated.does_not_know
    assert "已确认不成立：巡查队只在白天巡逻" in updated.knows


def test_character_fields_and_chapter_stamp():
    lin = Character(name="林舟", false_beliefs=["巡查队只在白天巡逻"])
    chars, _ = apply_extraction([lin], {}, make_extraction())
    updated = chars[0]
    assert updated.current_goal == "查清是谁抹掉了父亲的档案"
    assert updated.status["位置"] == "城南旧仓库"
    assert updated.relationships["苏晚"] == "从怀疑转为初步合作"
    assert "巡查队只在白天巡逻" not in updated.false_beliefs
    assert "备用钥匙" in " ".join(updated.resources)
    assert updated.recent_change.startswith("[003]")


def test_unknown_character_is_recorded_not_silently_dropped():
    chars, state = apply_extraction([], {}, make_extraction())
    assert all(c.name != "路人甲" for c in chars)
    recorded = {row["name"] for row in state["unapplied_updates"]}
    assert {"林舟", "路人甲"} <= recorded


def test_state_merges_are_idempotent():
    extraction = make_extraction()
    _, state_once = apply_extraction([], {}, extraction)
    _, state_twice = apply_extraction([], state_once, extraction)
    assert len(state_twice["facts"]) == len(state_once["facts"])
    assert len(state_twice["timeline"]) == len(state_once["timeline"])
    assert len(state_twice["open_threads"]) == len(state_once["open_threads"])
    assert len(state_twice["foreshadowing"]) == 1


def test_locked_character_is_skipped_and_recorded():
    lin = Character(name="林舟", locked=True)
    chars, state = apply_extraction([lin], {}, make_extraction())
    updated = next(c for c in chars if c.name == "林舟")
    # 锁定人物卡片逐字段保持原样
    assert updated.model_dump() == lin.model_dump()
    reasons = {row["name"]: row["reason"] for row in state["unapplied_updates"]}
    assert reasons["林舟"] == "人物已锁定，回写跳过"


def test_unlock_after_lock_resumes_writeback():
    lin = Character(name="林舟", locked=True)
    _, state = apply_extraction([lin], {}, make_extraction())
    lin_unlocked = lin.model_copy(update={"locked": False})
    chars, state2 = apply_extraction([lin_unlocked], state, make_extraction())
    updated = next(c for c in chars if c.name == "林舟")
    assert updated.current_goal == "查清是谁抹掉了父亲的档案"
    assert state2["unapplied_updates"] == state["unapplied_updates"]  # 历史记录保留，不再新增


def test_foreshadow_status_advances_by_id():
    extraction = make_extraction()
    _, state = apply_extraction([], {}, extraction)
    extraction2 = make_extraction()
    extraction2.foreshadowing[0].status = "resolved"
    _, state2 = apply_extraction([], state, extraction2)
    assert state2["foreshadowing"][0]["status"] == "resolved"
