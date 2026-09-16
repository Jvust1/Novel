import subprocess
import sys
from pathlib import Path

from novel_ai.eval import RUBRIC_KEYS, make_scoring_sheet

REPO = Path(__file__).resolve().parents[1]


def write_sheet_with_scores(path: Path, fill: dict[tuple[str, str], int]) -> Path:
    """Copy the blank sheet and fill one dimension per (case, variant)."""
    run_record = {
        "run_id": "run-test",
        "cases": [
            {"case_id": "urban_dispute", "variant": "A_baseline"},
            {"case_id": "urban_dispute", "variant": "B_memory"},
        ],
    }
    sheet = make_scoring_sheet(run_record, path)
    lines = sheet.read_text(encoding="utf-8-sig").splitlines()
    out = [lines[0]]
    for line in lines[1:]:
        parts = line.split(",")
        key = (parts[1], parts[2])
        if parts[3] == "plot_pull" and key in fill:
            parts[5] = str(fill[key])
        out.append(",".join(parts))
    filled = path.parent / "filled.csv"
    filled.write_text("\n".join(out) + "\n", encoding="utf-8")
    return filled


def run_cli(sheet: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "aggregate_scores.py"), str(sheet)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO,
    )


def test_cli_aggregates_and_reports_missing_dimensions(tmp_path):
    filled = write_sheet_with_scores(tmp_path / "sheet.csv", {("urban_dispute", "A_baseline"): 4})
    # 同目录放 run.json，覆盖度检查以运行记录的 case/variant 网格为准
    (tmp_path / "run.json").write_text(
        '{"run_id": "run-test", "cases": ['
        '{"case_id": "urban_dispute", "variant": "A_baseline"},'
        '{"case_id": "urban_dispute", "variant": "B_memory"}]}',
        encoding="utf-8",
    )
    result = run_cli(filled)
    assert result.returncode == 0, result.stderr
    assert '"plot_pull": 4.0' in result.stdout
    assert "urban_dispute|A_baseline: 缺 11 项" in result.stdout
    assert "urban_dispute|B_memory: 缺 12 项" in result.stdout
    assert "存在未评分项" in result.stderr


def test_cli_rejects_empty_sheet(tmp_path):
    run_record = {"run_id": "run-test", "cases": [{"case_id": "x", "variant": "A_baseline"}]}
    sheet = make_scoring_sheet(run_record, tmp_path / "blank.csv")
    result = run_cli(sheet)
    assert result.returncode == 2
    assert "没有任何已填分数" in result.stderr


def test_rubric_covers_twelve_dimensions():
    assert len(RUBRIC_KEYS) == 12
    assert len(set(RUBRIC_KEYS)) == 12
