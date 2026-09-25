"""Aggregate a completed blind scoring sheet for one benchmark run.

Usage from repo root:

    python scripts/aggregate_blind_scores.py runs/<run_id> [--write]

The command refuses partial grids. With --write it stores
blind_scores_summary.json next to the run metadata.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novel_ai.blind_scoring import aggregate_blind_scores, blind_score_status  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    sheet = args.run_dir / "blind_scoring_sheet.csv"
    blind_map = args.run_dir / "blind_map.json"
    if not sheet.exists() or not blind_map.exists():
        print(
            "缺少 blind_scoring_sheet.csv 或 blind_map.json；请先运行 render_blind_scoring_pack.py",
            file=sys.stderr,
        )
        return 2

    try:
        status = blind_score_status(sheet, blind_map)
        if not status["complete"]:
            print(
                f"评分未完成：{status['scored_rows']}/{status['expected_rows']}，"
                f"仍缺 {len(status['missing'])} 项。",
                file=sys.stderr,
            )
            return 2
        summary = aggregate_blind_scores(sheet, blind_map)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"聚合失败: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    print(payload)
    if args.write:
        out = args.run_dir / "blind_scores_summary.json"
        out.write_text(payload + "\n", encoding="utf-8")
        print(f"已写入：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
