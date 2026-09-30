from novel_ai.models import ChapterPlan, SceneBeat
from novel_ai.story_dna import story_dna_from_plan, story_graph_to_kag_records
from novel_ai.workflow_guard import validate_plan_stage, workflow_summary


def make_plan():
    return ChapterPlan(
        chapter_title="夜访",
        chapter_promise="发现档案异常",
        tension_curve="潜入→暴露→逃离",
        scenes=[SceneBeat(
            scene_no=1,pov="林舟",place="档案室",time="夜",
            objective="查档案",opposition="巡查",choice="继续深入",
            cost="受伤",state_change="确认记录被抹去",end_hook="门外出现脚步声"
        )],
    )


def test_story_dna_from_plan():
    dna=story_dna_from_plan(make_plan())
    assert dna.event_sequence
    assert dna.choice_count == 1
    assert dna.state_change_count == 1


def test_workflow_plan_gate():
    assert validate_plan_stage(make_plan()).ok
    summary=workflow_summary(make_plan(),"正文。"*1000,target_chars=2000)
    assert "stages" in summary


def test_kag_record_export_is_plain_data():
    records=story_graph_to_kag_records({"nodes":[{"id":"character:林舟","type":"character","label":"林舟"}],"edges":[]})
    assert records[0]["record_type"]=="node"
