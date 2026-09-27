from __future__ import annotations

import argparse
from pathlib import Path

from novel_ai.reference_pack import build_reference_pack, save_reference_pack


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a non-reversible Novel Reference Pack.")
    parser.add_argument("files", nargs="+", help="TXT/MD/DOCX/PDF reference files")
    parser.add_argument("--name", default="reference-pack")
    parser.add_argument("--out", default="reference_pack.json")
    parser.add_argument("--weight", type=float, default=1.0, help="default weight for all inputs")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sources = []
    for raw in args.files:
        path = Path(raw)
        sources.append((path.name, path.read_bytes(), args.weight))
    pack = build_reference_pack(sources, name=args.name)
    target = save_reference_pack(pack, args.out)
    print(f"Wrote {target} with {pack.source_count} reference sources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
