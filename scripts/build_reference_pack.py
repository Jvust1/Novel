from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from novel_ai.reference_evidence import (
    DEFAULT_CHUNK_CHARS,
    DEFAULT_LAMBDA_MULT,
    DEFAULT_MAX_EXCERPT_CHARS,
    DEFAULT_TOP_N,
    MAX_SOURCE_BYTES,
    MAX_TOTAL_SOURCE_BYTES,
    build_reference_evidence,
)
from novel_ai.reference_pack import build_reference_pack, save_reference_pack


def read_query_sources_bounded(
    paths: list[Path] | tuple[Path, ...],
    *,
    max_source_bytes: int = MAX_SOURCE_BYTES,
    max_total_bytes: int = MAX_TOTAL_SOURCE_BYTES,
) -> list[tuple[Path, bytes]]:
    """Read query inputs with pre-stat and bounded streaming.

    Every file is stat'ed before opening.  Reads request at most one byte past
    the remaining allowance, so a file that grows after stat is rejected
    without handing any bytes to an extractor or Reference Pack builder.
    """
    if type(max_source_bytes) is not int or max_source_bytes <= 0:
        raise ValueError("max_source_bytes must be a positive integer")
    if type(max_total_bytes) is not int or max_total_bytes <= 0:
        raise ValueError("max_total_bytes must be a positive integer")
    total = 0
    result: list[tuple[Path, bytes]] = []
    for raw_path in paths:
        path = Path(raw_path)
        try:
            info = path.stat()
        except OSError as exc:
            raise ValueError(f"无法检查参考源: {path}") from exc
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise ValueError(f"输入必须是普通文件: {path}")
        if info.st_size > max_source_bytes:
            raise ValueError(f"参考源超过单文件资源上限: {path}")
        if info.st_size > max_total_bytes - total:
            raise ValueError(f"参考源超过累计资源上限: {path}")

        file_total = 0
        chunks: list[bytes] = []
        with path.open("rb") as handle:
            while True:
                remaining_file = max_source_bytes - file_total
                remaining_total = max_total_bytes - total
                if remaining_file < 0 or remaining_total < 0:
                    raise ValueError(f"参考源超过资源上限: {path}")
                read_size = min(1024 * 1024, remaining_file, remaining_total) + 1
                chunk = handle.read(read_size)
                if not chunk:
                    break
                file_total += len(chunk)
                total += len(chunk)
                if file_total > max_source_bytes:
                    raise ValueError(f"参考源超过单文件资源上限: {path}")
                if total > max_total_bytes:
                    raise ValueError("参考源超过累计资源上限")
                chunks.append(chunk)
        result.append((path, b"".join(chunks)))
    return result


def _reject_query_output_collisions(
    pack_target: Path,
    evidence_target: Path,
    source_paths: list[Path],
) -> None:
    """Reject query outputs that exist or share an inode with an input."""
    if pack_target.resolve(strict=False) == evidence_target.resolve(strict=False):
        raise ValueError("query 的两个输出路径不能相同")
    for target, label in ((pack_target, "Reference Pack"), (evidence_target, "evidence")):
        target_resolved = target.resolve(strict=False)
        for source in source_paths:
            source_resolved = source.resolve(strict=True)
            try:
                same_inode = target.samefile(source)
            except FileNotFoundError:
                same_inode = False
            except OSError as exc:
                raise ValueError(f"无法检查 {label} 输出与参考源的 inode 关系") from exc
            if same_inode or target_resolved == source_resolved:
                raise ValueError(f"{label} 输出不得覆盖或别名指向参考源文件")
        if target.exists() or target.is_symlink():
            raise ValueError(f"{label} 输出已存在，查询模式拒绝覆盖: {target}")


def _stage_query_json(target: Path, text: str) -> Path:
    """Stage one complete query artifact beside its eventual target."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_stage = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    stage = Path(raw_stage)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            stage.unlink()
        except FileNotFoundError:
            pass
        raise
    return stage


def _publish_query_stage(stage: Path, target: Path) -> os.stat_result:
    """Publish a staged query file with exclusive, no-clobber creation."""
    owner_stat = os.stat(stage, follow_symlinks=False)
    try:
        os.link(stage, target)
    except FileExistsError as exc:
        raise ValueError(f"query 输出已存在，拒绝覆盖: {target}") from exc
    except OSError as exc:
        raise OSError(f"无法以独占方式发布 query 输出: {target}") from exc
    try:
        stage.unlink()
    except FileNotFoundError:
        pass
    return owner_stat


def _remove_query_owner(target: Path, owner_stat: os.stat_result) -> None:
    """Remove only a file whose inode is the one this invocation published."""
    try:
        current = os.stat(target, follow_symlinks=False)
        if os.path.samestat(current, owner_stat):
            target.unlink()
    except (FileNotFoundError, OSError):
        # A missing path or a concurrent replacement belongs to the other
        # writer and must remain untouched.
        pass


def _publish_query_outputs(pack: object, evidence: dict, pack_target: Path, evidence_target: Path) -> None:
    """Stage both query artifacts, then publish with bounded cleanup.

    This is intentionally query-specific.  It does not provide a cross-file
    transaction: if the second exclusive publish fails, only the first file
    still owned by this invocation is removed.
    """
    stages: list[Path] = []
    owned: list[tuple[Path, os.stat_result]] = []
    try:
        pack_stage = _stage_query_json(pack_target, pack.model_dump_json(indent=2))
        stages.append(pack_stage)
        evidence_stage = _stage_query_json(
            evidence_target,
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        )
        stages.append(evidence_stage)
        owned.append((pack_target, _publish_query_stage(pack_stage, pack_target)))
        owned.append((evidence_target, _publish_query_stage(evidence_stage, evidence_target)))
    except BaseException:
        for target, owner_stat in reversed(owned):
            _remove_query_owner(target, owner_stat)
        raise
    finally:
        for stage in stages:
            try:
                stage.unlink()
            except FileNotFoundError:
                pass


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
        evidence_target = None
        if args.evidence_out is not None:
            evidence_target = Path(args.evidence_out)
            _reject_query_output_collisions(pack_target, evidence_target, input_paths)

        choices = {}
        for raw, codec in args.encoding or []:
            path = Path(raw).resolve()
            if path not in inputs or path in choices:
                raise ValueError("编码选择必须唯一且对应本次输入文件")
            choices[path] = codec
        sources = []
        evidence_sources = []
        evidence = None
        if args.query is not None:
            # This must be the first operation that touches source bytes in
            # query mode.  No extractor or pack builder runs until every file
            # has passed stat and bounded streaming checks.
            bounded_sources = read_query_sources_bounded(input_paths)
            for path, data in bounded_sources:
                selected_encoding = choices.get(path.resolve())
                sources.append((path.name, data, args.weight, selected_encoding))
                evidence_sources.append((path.name, data, selected_encoding))
            evidence = build_reference_evidence(
                evidence_sources,
                args.query,
                top_n=args.top_n,
                chunk_chars=args.chunk_chars,
                max_excerpt_chars=args.max_excerpt_chars,
                lambda_mult=args.lambda_mult,
            )
            pack = build_reference_pack(sources, name=args.name)
        else:
            for path in input_paths:
                data = path.read_bytes()
                selected_encoding = choices.get(path.resolve())
                sources.append((path.name, data, args.weight, selected_encoding))
            pack = build_reference_pack(sources, name=args.name)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        if evidence is not None and evidence_target is not None:
            _publish_query_outputs(pack, evidence, pack_target, evidence_target)
            target = pack_target
        else:
            # Preserve the legacy non-query writer and its overwrite behavior.
            target = save_reference_pack(pack, args.out)
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
