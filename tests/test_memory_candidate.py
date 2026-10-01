import copy

import pytest

from novel_ai.memory_candidate import (
    MemoryCandidateError,
    acceptance_receipt,
    build_memory_candidate,
    chapter_text_sha256,
    receipt_matches,
    validate_memory_candidate,
)
from novel_ai.models import MemoryExtraction


def extraction(chapter_id="007"):
    return MemoryExtraction(
        chapter_id=chapter_id,
        summary="沈青确认账本由林澄保管。",
        new_facts=["账本由林澄保管"],
    )


def test_candidate_binds_exact_project_chapter_text_and_extraction():
    candidate = build_memory_candidate("Book-A", "007", "正文", extraction())
    assert candidate["project"] == "Book-A"
    assert candidate["chapter_id"] == "007"
    assert candidate["chapter_text_sha256"] == chapter_text_sha256("正文")
    assert candidate["candidate_id"].startswith("memory-candidate-")
    restored = validate_memory_candidate(candidate, project="Book-A", chapter_id="007", chapter_text="正文")
    assert restored.summary == "沈青确认账本由林澄保管。"


@pytest.mark.parametrize("field,value,error", [
    ("project", "Book-B", "another project"),
    ("chapter_id", "008", "another chapter"),
    ("text", "正文已修改", "different chapter revision"),
])
def test_candidate_cannot_cross_project_chapter_or_revision(field, value, error):
    candidate = build_memory_candidate("Book-A", "007", "正文", extraction())
    kwargs = {"project": "Book-A", "chapter_id": "007", "chapter_text": "正文"}
    if field == "text":
        kwargs["chapter_text"] = value
    else:
        kwargs[field] = value
    with pytest.raises(MemoryCandidateError, match=error):
        validate_memory_candidate(candidate, **kwargs)


def test_tampered_candidate_and_wrong_extraction_chapter_are_refused():
    candidate = build_memory_candidate("Book-A", "007", "正文", extraction())
    tampered = copy.deepcopy(candidate)
    tampered["extraction"]["new_facts"] = ["未获作者确认的替换事实"]
    with pytest.raises(MemoryCandidateError, match="integrity"):
        validate_memory_candidate(tampered, project="Book-A", chapter_id="007", chapter_text="正文")
    with pytest.raises(MemoryCandidateError, match="chapter_id"):
        build_memory_candidate("Book-A", "007", "正文", extraction("008"))


def test_acceptance_receipt_is_candidate_specific_and_old_confirmation_cannot_authorize_new_candidate():
    first = build_memory_candidate("Book-A", "007", "正文", extraction())
    second = build_memory_candidate(
        "Book-A", "007", "正文",
        MemoryExtraction(chapter_id="007", summary="另一候选"),
    )
    receipt = acceptance_receipt(first)
    assert receipt_matches(receipt, first)
    assert not receipt_matches(receipt, second)
    assert receipt["confirmed_by"] == "author"
    assert receipt["confirmation_source"] == "local-workbench-confirm-button"


def test_receipt_tampering_and_candidate_tampering_never_match():
    candidate = build_memory_candidate("Book-A", "007", "正文", extraction())
    receipt = acceptance_receipt(candidate)
    changed_receipt = copy.deepcopy(receipt)
    changed_receipt["candidate_id"] = "memory-candidate-" + "0" * 64
    assert not receipt_matches(changed_receipt, candidate)
    changed_candidate = copy.deepcopy(candidate)
    changed_candidate["chapter_text_sha256"] = "0" * 64
    assert not receipt_matches(receipt, changed_candidate)
