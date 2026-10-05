from novel_ai.engine import ChapterResult
from novel_ai.longform_consistency import behavior_review_payload, voice_review_payload


def test_chapter_result_accepts_longform_reports():
    assert "voice_dna_report" in ChapterResult.__dataclass_fields__
    assert "behavior_repetition_report" in ChapterResult.__dataclass_fields__


def test_longform_review_payloads_use_review_issue_shape():
    b=behavior_review_payload({"alerts":[{"character":"林舟","chapter_id":"003","score":0.9}]})
    v=voice_review_payload([{"character":"苏晚","score":0.6,"reason":"漂移","suggestion":"核对"}])
    assert b["issues"][0]["category"]=="人物行为模式重复"
    assert v["issues"][0]["category"]=="人物口吻漂移"
