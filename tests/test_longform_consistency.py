from novel_ai.longform_consistency import (
    character_voice_dna, behavior_repetition, timeline_contradictions,
    foreshadow_lifecycle, tension_density,
)


def test_character_voice_dna_extracts_attributed_dialogue():
    text='林舟说：“你先走。”\n“我不走。”林舟低声说。'
    dna=character_voice_dna(text,["林舟"])
    assert dna["林舟"]["line_count"] >= 2


def test_behavior_repetition_same_character():
    current={"beats":[{"pov":"林舟","objective":"赴约","opposition":"被跟踪","choice":"仍然赴约","cost":"丢失证件","state_change":"得到地址"}]}
    history=[{"chapter_id":"003","story_dna":{"beats":[{"pov":"林舟","objective":"赴约","opposition":"遭跟踪","choice":"坚持赴约","cost":"丢失证件","state_change":"获得地址"}]}}]
    report=behavior_repetition(current,history,threshold=0.5)
    assert report["should_avoid"]


def test_timeline_reversal_detected():
    state={"timeline":[
        {"chapter_id":"1","description":"启程","time_hint":"第3天"},
        {"chapter_id":"2","description":"抵达","time_hint":"第2天"},
    ]}
    assert timeline_contradictions(state)


def test_foreshadow_overdue_and_tension_density():
    state={"foreshadowing":[{"id":"k","description":"钥匙","status":"planted","planted_chapter":"001"}]}
    order=[f"{i:03d}" for i in range(1,15)]
    life=foreshadow_lifecycle(state,order)
    assert life["overdue"]
    history=[{"chapter_id":str(i),"story_dna":{"beats":[{}],"hook_count":1,"choice_count":1,"cost_count":1,"state_change_count":1,"tension_curve":"高潮"}} for i in range(6)]
    density=tension_density(history)
    assert density["warnings"]
