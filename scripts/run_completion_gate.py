from __future__ import annotations

import argparse
import json
from pathlib import Path

from novel_ai.completion_gate import run_quality_gate


def _read_md_dir(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {
        p.stem: p.read_text(encoding="utf-8")
        for p in sorted(path.glob("*.md"))
        if p.is_file()
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Novel deterministic long-form quality gate"
    )
    parser.add_argument("--chapters", required=True)
    parser.add_argument("--critics")
    parser.add_argument("--min-chapter-units", type=int, default=800)
    parser.add_argument("--output")
    args = parser.parse_args()

    chapters = _read_md_dir(Path(args.chapters))
    if not chapters:
        raise SystemExit("No chapter .md files found")
    critics = _read_md_dir(Path(args.critics)) if args.critics else {}
    report = run_quality_gate(
        chapters, critics, min_chapter_units=args.min_chapter_units
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
