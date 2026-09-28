from __future__ import annotations

import argparse
from pathlib import Path

from novel_ai.story_dna import build_story_dna, save_story_dna


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a non-reversible Novel Story DNA profile.")
    parser.add_argument("files", nargs="+", help="TXT/MD/DOCX/PDF reference files")
    parser.add_argument("--name", default="story-dna")
    parser.add_argument("--out", default="story_dna.json")
    parser.add_argument("--weight", type=float, default=1.0)
    args = parser.parse_args()

    sources = [
        (path.name, path.read_bytes(), args.weight)
        for raw in args.files
        for path in [Path(raw)]
    ]
    dna = build_story_dna(sources, name=args.name)
    target = save_story_dna(dna, args.out)
    print(f"Wrote {target} with {dna.source_count} reference sources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
