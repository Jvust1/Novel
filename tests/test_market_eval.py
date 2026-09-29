import csv
import json
import subprocess
import sys
from pathlib import Path

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


def test_market_review_cli_creates_and_aggregates_sheet(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    sample = corpus()
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(sample.model_dump_json(), encoding="utf-8")
    sheet_path = tmp_path / "scores.csv"
    output_path = tmp_path / "summary.json"
    repo_root = Path(__file__).parents[1]
    command = [
        sys.executable,
        str(repo_root / "scripts" / "market_review.py"),
        str(corpus_path),
        "--sheet",
        str(sheet_path),
    ]

    created = subprocess.run(command, cwd=repo_root, capture_output=True, text=True, check=True)
    assert "Blank scoring sheet" in created.stdout
    assert sheet_path.exists()
    with sheet_path.open(encoding="utf-8-sig", newline="") as handle:
        blank_rows = list(csv.DictReader(handle))
    assert all(row["score"] == "" for row in blank_rows)
    assert "测试正文" not in sheet_path.read_text(encoding="utf-8-sig")

    incomplete = subprocess.run(
        [*command, "--aggregate", "--out", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert incomplete.returncode != 0
    assert "评分表未填完" in incomplete.stderr
    assert "Traceback" not in incomplete.stderr
    assert not output_path.exists()

    fill_sheet(sheet_path, reviewer="reviewer-a", score="4")
    subprocess.run(
        [*command, "--aggregate", "--out", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    summary = json.loads(output_path.read_text(encoding="utf-8"))
    assert summary["corpus_sha256"] == sample.fingerprint()
    assert summary["reviewer_id"] == "reviewer-a"
    assert summary["mean_score"] == 4.0
    assert summary["publishability_verdict"] is None


def test_recreating_sheet_preserves_completed_scores(tmp_path):
    sample = corpus()
    sheet = make_market_scoring_sheet(sample, tmp_path / "scores.csv")
    fill_sheet(sheet)
    original = sheet.read_bytes()
    with pytest.raises(FileExistsError):
        make_market_scoring_sheet(sample, sheet)
    assert sheet.read_bytes() == original


def edit_sheet(path, change):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    change(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerows(rows)


@pytest.mark.parametrize(
    "kind, message",
    [
        ("duplicate_header", "重复列名"),
        ("missing_header", "缺少必需列.*reviewer_id"),
        ("blank_header", "空列名"),
        ("extra_cell", "第 2 行.*列数"),
        ("missing_cell", "第 2 行.*列数"),
        ("empty_file", "表头"),
        ("broken_quote", "CSV 格式错误"),
    ],
)
def test_rejects_malformed_csv(tmp_path, kind, message):
    sample = corpus()
    sheet = make_market_scoring_sheet(sample, tmp_path / "scores.csv")
    fill_sheet(sheet)

    def change(rows):
        if kind == "duplicate_header":
            for row in rows:
                row.append(row[6])
        elif kind == "missing_header":
            for row in rows:
                row.pop(3)
        elif kind == "blank_header":
            rows[0][-1] = ""
        elif kind == "extra_cell":
            rows[1].append("unexpected")
        elif kind == "missing_cell":
            rows[1].pop()

    edit_sheet(sheet, change)
    if kind == "empty_file":
        sheet.write_text("", encoding="utf-8")
    elif kind == "broken_quote":
        with sheet.open("a", encoding="utf-8") as handle:
            handle.write('"unterminated')
    with pytest.raises(ValueError, match=message):
        load_market_scores(sheet, sample)


@pytest.mark.parametrize("score", ["0", "6", "4.5", "four"])
def test_rejects_invalid_score_with_row_number(tmp_path, score):
    sample = corpus()
    sheet = make_market_scoring_sheet(sample, tmp_path / "scores.csv")
    fill_sheet(sheet, score=score)
    with pytest.raises(ValueError, match="第 2 行.*1.*5.*整数"):
        load_market_scores(sheet, sample)


def test_reviewer_whitespace_and_quoted_notes_roundtrip(tmp_path):
    sample = corpus()
    sheet = make_market_scoring_sheet(sample, tmp_path / "scores.csv")
    fill_sheet(sheet)
    note = '开场清晰, "转折"需要铺垫\n第二条建议'

    def change(rows):
        rows[1][3] = " reviewer-a "
        rows[1][7] = note

    edit_sheet(sheet, change)
    rows = load_market_scores(sheet, sample)
    assert rows[0].note == note
    assert aggregate_market_scores(rows)["reviewer_id"] == "reviewer-a"


def cli_command(corpus_path, sheet_path):
    repo_root = Path(__file__).resolve().parents[1]
    return [
        sys.executable, str(repo_root / "scripts" / "market_review.py"),
        str(corpus_path), "--sheet", str(sheet_path),
    ]


@pytest.mark.parametrize("target", ["corpus", "sheet", "summary"])
def test_cli_preserves_existing_output_and_input_files(tmp_path, target):
    sample = corpus()
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(sample.model_dump_json(), encoding="utf-8")
    sheet = make_market_scoring_sheet(sample, tmp_path / "scores.csv")
    fill_sheet(sheet)
    summary = tmp_path / "summary.json"
    summary.write_text('{"previous_review": true}', encoding="utf-8")
    paths = {"corpus": corpus_path, "sheet": sheet, "summary": summary}
    originals = {key: path.read_bytes() for key, path in paths.items()}
    command = cli_command(corpus_path, sheet)
    commands = [
        [*command, "--aggregate", "--out", str(paths[target])],
        cli_command(corpus_path, paths[target]),
    ]
    for command in commands:
        result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
        assert result.returncode == 2
        assert "已存在" in result.stderr
        assert "Traceback" not in result.stderr
        assert {key: path.read_bytes() for key, path in paths.items()} == originals


def test_cli_rejects_malformed_csv_without_writing_summary(tmp_path):
    sample = corpus()
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(sample.model_dump_json(), encoding="utf-8")
    sheet = tmp_path / "scores.csv"
    sheet.write_text('"unterminated', encoding="utf-8")
    summary = tmp_path / "summary.json"
    result = subprocess.run(
        [*cli_command(corpus_path, sheet), "--aggregate", "--out", str(summary)],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "CSV 格式错误" in result.stderr
    assert "Traceback" not in result.stderr
    assert not summary.exists()


def test_cli_requires_aggregate_for_output_path(tmp_path):
    sample = corpus()
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(sample.model_dump_json(), encoding="utf-8")
    sheet = tmp_path / "scores.csv"
    summary = tmp_path / "summary.json"
    result = subprocess.run(
        [*cli_command(corpus_path, sheet), "--out", str(summary)],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "--out" in result.stderr and "--aggregate" in result.stderr
    assert not sheet.exists()
    assert not summary.exists()
