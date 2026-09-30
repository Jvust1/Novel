from novel_ai.longform_analytics import (
    chapter_analytics, cluster_story_dna, trope_frequency, detect_longform_drift,
)


def dna(chapter, event, tension="rise"):
    return {"chapter_id":chapter,"story_dna":{
        "event_sequence":[event],"tension_curve":tension,"beats":[{"end_hook":"电话响起"}],
        "hook_count":1,"choice_count":1,"cost_count":1,"state_change_count":1,
    }}


def test_trope_frequency_counts_repeated_patterns():
    rows=[dna("1","赴约"),dna("2","赴约"),dna("3","争吵","fall")]
    stats=trope_frequency(rows)
    assert stats["chapter_count"]==3
    assert stats["tension_curves"]["rise"]==2


def test_story_dna_clustering_returns_all_chapters():
    rows=[dna("1","收到电话去仓库"),dna("2","接到电话去仓库"),dna("3","家宴争吵离席")]
    clusters=cluster_story_dna(rows)
    assert sum(c["size"] for c in clusters)==3


def test_chapter_analytics_and_drift_shape():
    a=chapter_analytics("001","他推开门。\n\n电话响了。",dna("1","x")["story_dna"])
    assert a.chapter_id=="001"
    assert isinstance(detect_longform_drift([{"analytics":a.to_dict()}]),list)
