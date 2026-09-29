from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# Allow direct execution from the repository checkout: python scripts/build_release_pack.py
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from novel_ai.market_eval import load_market_corpus
from novel_ai.release_pack import MarketProfile, build_release_pack, save_release_pack


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a metadata-only Novel market release pack.")
    parser.add_argument("corpus", type=Path, help="Validated 3- or 20-chapter corpus JSON")
    parser.add_argument("metadata", type=Path, help="JSON with profile and explicit release copy")
    parser.add_argument("--out", type=Path, default=Path("release_pack.json"))
    args = parser.parse_args()

    try:
        corpus = load_market_corpus(args.corpus)
        metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("元数据必须是 JSON 对象")
        profile = MarketProfile.model_validate(metadata["profile"])
        pack = build_release_pack(
            corpus,
            profile,
            title=metadata["title"],
            one_line_hook=metadata["one_line_hook"],
            short_blurb=metadata["short_blurb"],
            long_blurb=metadata.get("long_blurb", ""),
            tags=metadata.get("tags", []),
            content_warnings=metadata.get("content_warnings", []),
            manual_checks=metadata.get("manual_checks", []),
        )
        target = save_release_pack(pack, args.out)
        print(f"Wrote {target}; corpus={pack.corpus_sha256[:12]}…")
        return 0
    except FileExistsError as exc:
        parser.error(f"输出文件已存在，请更换文件名：{exc.filename}")
    except (KeyError, OSError, TypeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
