"""Render the human scoring pack for a benchmark run.

Usage (from repo root):

    python scripts/render_scoring_pack.py runs/<run_id>

Writes scoring_pack.md next to run.json: per case, the chapter goal and both
variants' full text, plus the 12-dimension rubric with anchors.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novel_ai.eval import render_scoring_pack  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: python scripts/render_scoring_pack.py runs/<run_id>", file=sys.stderr)
        return 2
    run_dir = Path(sys.argv[1])
    if not (run_dir / "run.json").exists():
        print(f"找不到 {run_dir / 'run.json'}", file=sys.stderr)
        return 2
    out = render_scoring_pack(run_dir)
    print(f"评分包已生成：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
