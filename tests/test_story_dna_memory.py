from novel_ai.story_dna_memory import compare_story_dna, story_dna_review_payload


def dna(events, tension="rise-fall", hooks=1, choices=1, costs=1, changes=1):
    return {
        "event_sequence": events,
        "tension_curve": tension,
        "hook_count": hooks,
        "choice_count": choices,
        "cost_count": costs,
        "state_change_count": changes,
    }


def test_story_dna_repeat_is_detected():
    current = dna(["收到匿名电话 | 被跟踪 | 选择赴约 | 失去证件 | 得到仓库地址"])
    history = [{
        "chapter_id": "003",
        "story_dna": dna(["接到匿名来电 | 遭人跟踪 | 决定赴约 | 丢失证件 | 获得仓库地址"]),
    }]
    report = compare_story_dna(current, history, threshold=0.55)
    assert report.should_avoid
    assert report.matches[0].chapter_id == "003"
    assert story_dna_review_payload(report)["issues"]


def test_unrelated_story_dna_passes():
    current = dna(["参加家宴 | 隐瞒病情 | 选择离席 | 失去信任 | 决定道歉"])
    history = [{
        "chapter_id": "001",
        "story_dna": dna(["潜入仓库 | 触发警报 | 选择断电 | 丢掉手机 | 翻窗逃走"], tension="steady-rise"),
    }]
    report = compare_story_dna(current, history)
    assert report.max_score < 0.72
