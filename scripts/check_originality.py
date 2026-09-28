from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from novel_ai.originality import evaluate_originality
from novel_ai.reading import extract_reference_text


def _read(path: Path) -> str:
    return extract_reference_text(path.name, path.read_bytes())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the four-layer Novel originality Gate.")
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path, action="append")
    parser.add_argument("--strict", action="store_true", help="Require a configured embedding encoder.")
    parser.add_argument("--output", type=Path, help="Write the derived JSON result to this path.")
    args = parser.parse_args()

    target = _read(args.target)
    references = [_read(path) for path in args.reference]
    result = evaluate_originality(target, references, strict=args.strict)
    payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
