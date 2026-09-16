from novel_ai.context import ContextAssembler
from novel_ai.storage import ProjectStore


def seed_store(root):
    store = ProjectStore(root)
    store.save_story_state(
        "P",
        {
            "facts": ["北城冬天极冷", "男主有一条旧军毯"],
            "timeline": [{"chapter_id": "001", "description": "离家", "time_hint": "冬初"}],
            "foreshadowing": [
                {"id": "blanket", "description": "军毯上的编号", "status": "planted", "planted_chapter": "001"},
                {"id": "old-debt", "description": "旧债", "status": "resolved", "planted_chapter": "002"},
            ],
            "open_threads": ["军毯是谁留下的"],
        },
    )
    rows = [
        {"chapter_id": "001", "chapter_title": "离家", "summary": "第一" * 60},
        {"chapter_id": "002", "chapter_title": "进城", "summary": "第二" * 60},
        {"chapter_id": "003", "chapter_title": "夜谈", "summary": "第三" * 60},
    ]
    for row in rows:
        store.save_extraction("P", {"chapter_id": row["chapter_id"], "chapter_title": row["chapter_title"], "summary": row["summary"]})
    return store


def test_assemble_layers_and_resolved_foreshadowing_excluded(tmp_path):
    store = seed_store(tmp_path)
    ctx = ContextAssembler(store, "P").assemble(recent_limit=2)
    assert "军毯上的编号" in ctx.active_block
    assert "旧债" not in ctx.active_block
    assert "北城冬天极冷" in ctx.canon_block
    assert ctx.recent_summaries[-1]["chapter_id"] == "003"
    assert "001" in ctx.recall_block and "003" not in ctx.recall_block


def test_recall_block_respects_budget(tmp_path):
    store = seed_store(tmp_path)
    ctx = ContextAssembler(store, "P", recall_char_budget=60).assemble(recent_limit=1)
    assert len(ctx.recall_block) <= 80


def test_empty_project_produces_empty_blocks(tmp_path):
    store = ProjectStore(tmp_path)
    ctx = ContextAssembler(store, "Empty").assemble()
    assert ctx.canon_block == ""
    assert ctx.active_block == ""
    assert ctx.recall_block == ""
    assert ctx.recent_summaries == []
