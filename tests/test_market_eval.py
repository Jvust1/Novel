import csv

import pytest

from novel_ai.market_eval import (
    MARKET_RUBRIC,
    MarketChapter,
    MarketCorpus,
    aggregate_market_scores,
    load_market_scores,
    make_market_scoring_sheet,
)


def corpus(stage="opening_3"):
    count = 3 if stage == "opening_3" else 20
    return MarketCorpus(
        project="test-novel",
        stage=stage,
        chapters=[
            MarketChapter(number=index, title=f"第{index}章", text=f"第{index}章的测试正文。")
            for index in range(1, count + 1)
        ],
    )


def fill_sheet(path, reviewer="reviewer-a", score="4"):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    for row in rows:
        row["reviewer_id"] = reviewer
        row["score"] = score
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_opening_and_retention_stage_require_exact_chapter_counts():
    assert len(corpus("opening_3").validate_stage().chapters) == 3
    assert len(corpus("retention_20").validate_stage().chapters) == 20
    with pytest.raises(ValueError, match="恰好 20"):
        MarketCorpus(project="x", stage="retention_20", chapters=corpus().chapters).validate_stage()


def test_scoring_sheet_is_blank_and_bound_to_corpus(tmp_path):
    sample = corpus()
    sheet = make_market_scoring_sheet(sample, tmp_path / "market.csv")
    with sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(MARKET_RUBRIC)
    assert all(row["score"] == "" for row in rows)
    assert all(row["corpus_sha256"] == sample.fingerprint() for row in rows)
    assert "测试正文" not in sheet.read_text(encoding="utf-8-sig")


def test_only_complete_human_scores_can_be_aggregated(tmp_path):
    sample = corpus()
    sheet = make_market_scoring_sheet(sample, tmp_path / "market.csv")
    with pytest.raises(ValueError, match="未填完"):
        load_market_scores(sheet, sample)
    fill_sheet(sheet)
    rows = load_market_scores(sheet, sample)
    result = aggregate_market_scores(rows)
    assert result["mean_score"] == 4.0
    assert result["status"] == "human_review_recorded"
    assert result["publishability_verdict"] is None


def test_scores_reject_corpus_change_and_missing_identity(tmp_path):
    sample = corpus()
    sheet = make_market_scoring_sheet(sample, tmp_path / "market.csv")
    fill_sheet(sheet, reviewer="")
    with pytest.raises(ValueError, match="reviewer_id"):
        load_market_scores(sheet, sample)
    fill_sheet(sheet)
    changed = corpus()
    changed.chapters[0].text = "修改后的第一章。"
    with pytest.raises(ValueError, match="语料不匹配"):
        load_market_scores(sheet, changed)


def test_rejects_duplicate_or_missing_dimension(tmp_path):
    sample = corpus()
    sheet = make_market_scoring_sheet(sample, tmp_path / "market.csv")
    fill_sheet(sheet)
    with sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0])
    rows[0]["dimension"] = rows[1]["dimension"]
    with sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="缺失或重复"):
        load_market_scores(sheet, sample)
