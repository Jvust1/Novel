from novel_ai.context import ContextAssembler
from novel_ai.memory import apply_extraction
from novel_ai.models import ForeshadowItem, MemoryExtraction
from novel_ai.storage import ProjectStore


def test_longform_health_enters_context(tmp_path):
    store=ProjectStore(tmp_path)
    store.save_longform_health("p",{"guard_context":"【长篇一致性约束】\n- 时间线不要回退"})
    ctx=ContextAssembler(store,"p").assemble()
    assert "时间线不要回退" in ctx.prompt_sections()


def test_voice_dna_roundtrip(tmp_path):
    store=ProjectStore(tmp_path)
    store.save_voice_dna("p","001",{"林舟":{"line_count":3}})
    rows=store.load_voice_dna_history("p")
    assert rows[0]["voice_dna"]["林舟"]["line_count"]==3


def test_resolved_foreshadow_does_not_regress():
    state={"facts":[],"timeline":[],"open_threads":[],"foreshadowing":[{
        "id":"key","description":"钥匙","status":"resolved","planted_chapter":"001","last_chapter":"005"
    }]}
    extraction=MemoryExtraction(
        chapter_id="006",summary="x",
        foreshadowing=[ForeshadowItem(id="key",description="钥匙",status="advanced",chapter_id="006")]
    )
    _,new=apply_extraction([],state,extraction)
    item=new["foreshadowing"][0]
    assert item["status"]=="resolved"
    assert item["lifecycle_warnings"]
