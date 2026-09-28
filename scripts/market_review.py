from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# Support direct execution from a checkout: python scripts/market_review.py
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from novel_ai.market_eval import (
    aggregate_market_scores,
    load_market_corpus,
    load_market_scores,
    make_market_scoring_sheet,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or aggregate offline market-readability review.")
    parser.add_argument("corpus", type=Path, help="Owned chapter corpus JSON")
    parser.add_argument("--sheet", type=Path, required=True, help="CSV scoring sheet")
    parser.add_argument("--aggregate", action="store_true", help="Read a completed sheet instead of creating one")
    parser.add_argument("--out", type=Path, help="Write aggregate JSON")
    args = parser.parse_args()

    corpus = load_market_corpus(args.corpus)
    if not args.aggregate:
        path = make_market_scoring_sheet(corpus, args.sheet)
        print(f"Blank scoring sheet: {path}")
        return 0

    scores = load_market_scores(args.sheet, corpus)
    summary = aggregate_market_scores(scores)
    output = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
