from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from novel_ai.reference_pack import build_reference_pack, save_reference_pack


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a non-reversible Novel Reference Pack.")
    parser.add_argument("files", nargs="+", help="TXT/MD/DOCX/PDF reference files")
    parser.add_argument("--name", default="reference-pack")
    parser.add_argument("--out", default="reference_pack.json")
    parser.add_argument("--weight", type=float, default=1.0, help="default weight for all inputs")
    parser.add_argument("--encoding", nargs=2, action="append", metavar=("FILE", "ENCODING"),
                        help="Explicit TXT/MD codec for one input path; repeat for mixed-encoding files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        inputs = {Path(raw).resolve() for raw in args.files}
        choices = {}
        for raw, codec in args.encoding or []:
            path = Path(raw).resolve()
            if path not in inputs or path in choices:
                raise ValueError("编码选择必须唯一且对应本次输入文件")
            choices[path] = codec
        sources = []
        for raw in args.files:
            path = Path(raw)
            sources.append((path.name, path.read_bytes(), args.weight, choices.get(path.resolve())))
        pack = build_reference_pack(sources, name=args.name)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    target = save_reference_pack(pack, args.out)
    print(f"Wrote {target} with {pack.source_count} reference sources.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
