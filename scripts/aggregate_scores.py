"""Aggregate a filled benchmark scoring sheet.

Usage (from repo root):

    python scripts/aggregate_scores.py runs/<run_id>/scoring_sheet.csv
    python scripts/aggregate_scores.py runs/<run_id>/scoring_sheet.csv --write

Reads the human-filled CSV (12 dimensions x 1-5), checks coverage against the
run's case/variant grid, prints the aggregate JSON (including B-A delta), and
with --write saves scores_summary.json next to the sheet for ledger write-back.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novel_ai.eval import RUBRIC_KEYS, aggregate_scores, load_scores  # noqa: E402


def coverage_gaps(rows: list[dict], run_json: Path | None) -> list[str]:
    """Report (case, variant) pairs or dimensions that are missing scores."""
    scored = {(r["case_id"], r["variant"]) for r in rows}
    gaps: list[str] = []

    expected: list[tuple[str, str]] = []
    if run_json and run_json.exists():
        record = json.loads(run_json.read_text(encoding="utf-8"))
        expected = [(c["case_id"], c["variant"]) for c in record["cases"]]
    else:
        expected = sorted(scored)

    for case_id, variant in expected:
        dims = {r["dimension"] for r in rows if (r["case_id"], r["variant"]) == (case_id, variant)}
        missing = [d for d in RUBRIC_KEYS if d not in dims]
        if missing:
            gaps.append(f"{case_id}|{variant}: 缺 {len(missing)} 项 -> {', '.join(missing)}")
        elif not (case_id, variant) in scored:
            gaps.append(f"{case_id}|{variant}: 完全未评分")
    return gaps


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate a filled Novel benchmark scoring sheet")
    parser.add_argument("sheet", type=Path, help="path to filled scoring_sheet.csv")
    parser.add_argument("--write", action="store_true", help="write scores_summary.json next to the sheet")
    args = parser.parse_args()

    if not args.sheet.exists():
        print(f"找不到评分表：{args.sheet}", file=sys.stderr)
        return 2

    try:
        rows = load_scores(args.sheet)
    except ValueError as exc:
        print(f"评分表格式错误：{exc}", file=sys.stderr)
        return 2

    if not rows:
        print("评分表里还没有任何已填分数。", file=sys.stderr)
        return 2

    gaps = coverage_gaps(rows, args.sheet.parent / "run.json")
    summary = aggregate_scores(rows)
    summary["scored_rows"] = len(rows)
    summary["coverage_gaps"] = gaps

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if gaps:
        print("\n注意：存在未评分项；回填 EVALUATION_LEDGER 前建议补齐。", file=sys.stderr)

    if args.write:
        out = args.sheet.parent / "scores_summary.json"
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
