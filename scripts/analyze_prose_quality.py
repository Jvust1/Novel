from __future__ import annotations

import argparse
import json
from pathlib import Path

from novel_ai.quality_gate import analyze_prose_quality
from novel_ai.style_engine import detect_ai_flavor


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Novel prose with deterministic quality gates.")
    parser.add_argument("path", help="UTF-8 TXT/MD chapter or prose file")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    path = Path(args.path)
    text = path.read_text(encoding="utf-8")
    quality = analyze_prose_quality(text).to_dict()
    ai_flavor = detect_ai_flavor(text)
    payload = {"path": str(path), "quality": quality, "ai_flavor": ai_flavor}

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"quality_score: {quality['score']}")
        print(f"issues: {len(quality['issues'])}")
        print(f"backends: {quality['optional_backends']}")
        for issue in quality["issues"]:
            print(f"- [{issue['severity']}] {issue['category']}: {issue['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
