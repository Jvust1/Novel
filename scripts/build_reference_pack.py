from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from novel_ai.reference_evidence import (
    DEFAULT_CHUNK_CHARS,
    DEFAULT_LAMBDA_MULT,
    DEFAULT_MAX_EXCERPT_CHARS,
    DEFAULT_TOP_N,
    build_reference_evidence,
    save_evidence_artifact,
    validate_evidence_output_path,
)
from novel_ai.reference_pack import build_reference_pack, save_reference_pack


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a non-reversible Novel Reference Pack.")
    parser.add_argument("files", nargs="+", help="TXT/MD/DOCX/PDF reference files")
    parser.add_argument("--name", default="reference-pack")
    parser.add_argument("--out", default="reference_pack.json")
    parser.add_argument("--weight", type=float, default=1.0, help="default weight for all inputs")
    parser.add_argument("--encoding", nargs=2, action="append", metavar=("FILE", "ENCODING"),
                        help="Explicit TXT/MD codec for one input path; repeat for mixed-encoding files")
    parser.add_argument("--query", help="Optional local evidence query; must be paired with --evidence-out")
    parser.add_argument("--evidence-out", help="New private local JSON artifact for bounded evidence excerpts")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N,
                        help="evidence result count (1-20; requires --query and --evidence-out)")
    parser.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS,
                        help="evidence chunk bound in extracted Unicode characters")
    parser.add_argument("--max-excerpt-chars", type=int, default=DEFAULT_MAX_EXCERPT_CHARS,
                        help="maximum characters written per evidence excerpt")
    parser.add_argument("--lambda-mult", type=float, default=DEFAULT_LAMBDA_MULT,
                        help="MMR relevance/diversity weight between 0 and 1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if (args.query is None) != (args.evidence_out is None):
            raise ValueError("--query 与 --evidence-out 必须同时显式提供")

        input_paths = [Path(raw) for raw in args.files]
        inputs = {path.resolve() for path in input_paths}
        if len(inputs) != len(input_paths):
            raise ValueError("参考输入不能通过别名重复指定")
        for path in input_paths:
            if path.is_symlink() or not path.exists() or not path.is_file():
                raise ValueError(f"输入必须是普通文件: {path}")

        pack_target = Path(args.out)
        pack_resolved = pack_target.resolve(strict=False)
        if any(pack_resolved == path.resolve(strict=True) for path in input_paths):
            raise ValueError("Reference Pack 输出不得覆盖参考源文件")

        evidence_target = None
        if args.evidence_out is not None:
            evidence_target = validate_evidence_output_path(
                args.evidence_out, input_paths, pack_out=args.out
            )

        choices = {}
        for raw, codec in args.encoding or []:
            path = Path(raw).resolve()
            if path not in inputs or path in choices:
                raise ValueError("编码选择必须唯一且对应本次输入文件")
            choices[path] = codec
        sources = []
        evidence_sources = []
        for path in input_paths:
            data = path.read_bytes()
            selected_encoding = choices.get(path.resolve())
            sources.append((path.name, data, args.weight, selected_encoding))
            evidence_sources.append((path.name, data, selected_encoding))
        pack = build_reference_pack(sources, name=args.name)
        evidence = None
        if args.query is not None:
            evidence = build_reference_evidence(
                evidence_sources,
                args.query,
                top_n=args.top_n,
                chunk_chars=args.chunk_chars,
                max_excerpt_chars=args.max_excerpt_chars,
                lambda_mult=args.lambda_mult,
            )
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        target = save_reference_pack(pack, args.out)
        if evidence is not None and evidence_target is not None:
            save_evidence_artifact(evidence, evidence_target)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    message = f"Wrote {target} with {pack.source_count} reference sources."
    if evidence_target is not None:
        message += f" Wrote bounded evidence to {evidence_target}."
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
