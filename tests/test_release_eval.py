from novel_ai.release_eval import build_release_quality_snapshot, external_evaluator_capabilities

def test_release_snapshot():
    text="他推开门。屋里没人。\n\n电话响了。"
    s=build_release_quality_snapshot(text,previous_chapters=[("001",text)])
    assert 0 <= s.prose_score <= 100
    assert s.prior_chapter_similarity

def test_external_caps():
    c=external_evaluator_capabilities()
    assert set(c)=={"deepeval","ragas"}
