from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from novel_ai.originality import evaluate_originality
from novel_ai.reading import extract_reference
from novel_ai.text_decoding import TextDecodingError


def _read(path: Path, encoding: str | None = None):
    return extract_reference(path.name, path.read_bytes(), encoding=None if encoding == "auto" else encoding)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the four-layer Novel originality Gate.")
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path, action="append")
    parser.add_argument("--target-encoding", help="Explicit TXT/MD encoding; default accepts UTF-8/BOM only")
    parser.add_argument("--reference-encoding", action="append",
                        help="Repeat once per reference in order; use auto for UTF-8/BOM or non-text formats")
    parser.add_argument("--strict", action="store_true", help="Require a configured embedding encoder.")
    parser.add_argument("--output", type=Path, help="Write the derived JSON result to this path.")
    args = parser.parse_args()

    if args.reference_encoding is not None and len(args.reference_encoding) != len(args.reference):
        parser.error("--reference-encoding must be supplied once for each reference, in order")
    choices = args.reference_encoding or [None] * len(args.reference)
    try:
        target = _read(args.target, args.target_encoding)
        references = [_read(path, encoding) for path, encoding in zip(args.reference, choices)]
    except TextDecodingError as exc:
        parser.error(str(exc))
    result = evaluate_originality(target.text, [row.text for row in references], strict=args.strict)
    report = result.to_dict()
    report["input_decoding"] = {"target": target.decoding, "references": [row.decoding for row in references]}
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
