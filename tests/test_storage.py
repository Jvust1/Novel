from novel_ai.storage import ProjectStore


def test_replaying_an_older_extraction_keeps_chapter_order(tmp_path):
    store = ProjectStore(tmp_path)
    first = {"chapter_id": "001", "chapter_title": "起点", "summary": "第一章摘要"}
    second = {"chapter_id": "002", "chapter_title": "后果", "summary": "第二章摘要"}
    store.save_extraction("story", first)
    store.save_extraction("story", second)
    before = store.all_chapter_summaries("story")

    store.save_extraction("story", first)

    assert store.all_chapter_summaries("story") == before
    assert store.recent_chapter_summaries("story", limit=1) == [before[1]]


def test_correcting_an_older_summary_updates_it_in_place(tmp_path):
    store = ProjectStore(tmp_path)
    store.save_extraction("story", {"chapter_id": "001", "summary": "旧摘要"})
    store.save_extraction("story", {"chapter_id": "002", "summary": "后一章"})

    store.save_extraction("story", {"chapter_id": "001", "summary": "修订摘要"})

    rows = store.all_chapter_summaries("story")
    assert [row["chapter_id"] for row in rows] == ["001", "002"]
    assert rows[0]["summary"] == "修订摘要"
    assert store.read_json("story", "memory/extractions/001.json")["summary"] == "修订摘要"


def test_non_positive_summary_limit_returns_no_chapters(tmp_path):
    store = ProjectStore(tmp_path)
    store.save_extraction("story", {"chapter_id": "001", "summary": "第一章"})
    store.save_extraction("story", {"chapter_id": "002", "summary": "第二章"})
    assert store.recent_chapter_summaries("story", limit=0) == []
    assert store.recent_chapter_summaries("story", limit=-1) == []


def test_existing_duplicate_summary_rows_cannot_override_the_correction(tmp_path):
    store = ProjectStore(tmp_path)
    for row in [
        {"chapter_id": "001", "summary": "旧摘要"},
        {"chapter_id": "002", "summary": "后一章"},
        {"chapter_id": "001", "summary": "过期重复"},
    ]:
        store.append_jsonl("story", "memory/chapter_summaries.jsonl", row)

    store.save_extraction("story", {"chapter_id": "001", "summary": "修订摘要"})

    rows = store.all_chapter_summaries("story")
    assert [row["chapter_id"] for row in rows] == ["001", "002"]
    assert rows[0]["summary"] == "修订摘要"
    assert store.recent_chapter_summaries("story", limit=1)[0]["chapter_id"] == "002"
