from __future__ import annotations

import argparse
import json
from pathlib import Path

from novel_ai.models import ChapterPlan
from novel_ai.outline import build_hierarchical_outline, save_outline


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a DOC-style hierarchical Novel outline.")
    parser.add_argument("input", type=Path, help="JSON with title, premise and volumes")
    parser.add_argument("--out", default="hierarchical_outline.json")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    volumes = [
        (
            item.get("title", ""),
            [ChapterPlan.model_validate(chapter) for chapter in item.get("chapters", [])],
        )
        for item in payload.get("volumes", [])
    ]
    outline = build_hierarchical_outline(
        payload.get("title", ""),
        payload.get("premise", ""),
        volumes,
        notes=payload.get("notes", []),
    )
    target = save_outline(outline, args.out)
    print(f"Wrote {target} with {len(outline.flatten())} nodes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
