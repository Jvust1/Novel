"""Render an A/B-blind human scoring pack for one benchmark run.

Usage from repo root:

    python scripts/render_blind_scoring_pack.py runs/<run_id>

Writes three files next to run.json:
- blind_scoring_pack.md: safe to give to the scorer;
- blind_scoring_sheet.csv: score + rationale input;
- blind_map.json: unblinding key; keep closed until scoring is locked.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novel_ai.blind_scoring import render_blind_scoring_pack  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: python scripts/render_blind_scoring_pack.py runs/<run_id>", file=sys.stderr)
        return 2
    run_dir = Path(sys.argv[1])
    try:
        outputs = render_blind_scoring_pack(run_dir)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"生成失败: {exc}", file=sys.stderr)
        return 2
    print(f"盲化评分包：{outputs['pack']}")
    print(f"盲化评分表：{outputs['sheet']}")
    print(f"解盲映射（评分锁定前不要给评分者）：{outputs['map']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
