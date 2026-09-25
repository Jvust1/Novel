from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from .eval import RUBRIC, RUBRIC_KEYS, aggregate_scores, load_benchmark

SCHEMA_VERSION = "blind_scoring_v1"


def _opaque_sample_id(run_id: str, case_id: str, variant: str) -> str:
    """Return a stable opaque label for one frozen run sample."""
    payload = f"{SCHEMA_VERSION}|sample|{run_id}|{case_id}|{variant}".encode("utf-8")
    return f"S-{hashlib.sha256(payload).hexdigest()[:10].upper()}"


def _blind_order_key(run_id: str, case_id: str, variant: str) -> str:
    payload = f"{SCHEMA_VERSION}|order|{run_id}|{case_id}|{variant}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_blind_map(run_record: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic unblinding map without changing frozen run data."""
    run_id = str(run_record.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run.json 缺少 run_id")
    raw_cases = run_record.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("run.json 缺少 cases")

    seen_pairs: set[tuple[str, str]] = set()
    seen_sample_ids: set[str] = set()
    samples: list[dict[str, str]] = []
    for entry in raw_cases:
        case_id = str(entry.get("case_id") or "").strip()
        variant = str(entry.get("variant") or "").strip()
        if not case_id or not variant:
            raise ValueError("run.json 的 case 记录缺少 case_id/variant")
        pair = (case_id, variant)
        if pair in seen_pairs:
            raise ValueError(f"run.json 存在重复样本: {case_id}/{variant}")
        seen_pairs.add(pair)

        sample_id = _opaque_sample_id(run_id, case_id, variant)
        if sample_id in seen_sample_ids:
            raise ValueError(f"盲化 sample_id 冲突: {sample_id}")
        seen_sample_ids.add(sample_id)
        samples.append(
            {
                "sample_id": sample_id,
                "case_id": case_id,
                "variant": variant,
                "source_file": f"{case_id}__{variant}.txt",
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "samples": sorted(samples, key=lambda item: (item["case_id"], item["sample_id"])),
        "instructions": "评分锁定前不要向评分者展示此映射；它只用于完成后还原 variant 并聚合。",
    }


def _write_blind_sheet(run_id: str, samples: list[dict[str, str]], path: Path) -> Path:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "run_id",
                "case_id",
                "sample_id",
                "dimension_key",
                "dimension_label",
                "score",
                "rationale",
                "anchor",
            ]
        )
        for sample in samples:
            for item in RUBRIC:
                writer.writerow(
                    [
                        run_id,
                        sample["case_id"],
                        sample["sample_id"],
                        item["key"],
                        item["label"],
                        "",
                        "",
                        item["anchor"],
                    ]
                )
    return path


def render_blind_scoring_pack(run_dir: str | Path) -> dict[str, Path]:
    """Render an A/B-blind scoring pack, score sheet, and separate unblinding map.

    The scorer should receive only ``blind_scoring_pack.md`` and
    ``blind_scoring_sheet.csv``. ``blind_map.json`` intentionally contains the
    hidden mapping and should remain closed until scores are locked.
    """
    run_path = Path(run_dir)
    run_json = run_path / "run.json"
    if not run_json.exists():
        raise FileNotFoundError(f"找不到 {run_json}")
    record = json.loads(run_json.read_text(encoding="utf-8"))
    blind_map = build_blind_map(record)

    benchmark_dir = Path(__file__).resolve().parents[1] / "benchmarks"
    cases = (
        {case.case_id: case for case in load_benchmark(benchmark_dir)}
        if (benchmark_dir / "benchmark_manifest.json").exists()
        else {}
    )

    samples_by_case: dict[str, list[dict[str, str]]] = {}
    for sample in blind_map["samples"]:
        source = run_path / sample["source_file"]
        if not source.exists():
            raise FileNotFoundError(f"盲化评分缺少正文文件: {source}")
        samples_by_case.setdefault(sample["case_id"], []).append(sample)

    lines: list[str] = [
        f"# 盲化评分包 · {blind_map['run_id']}",
        "",
        "- 评分目标：同一用例的两个样本采用匿名标签；评分阶段不要查看 `blind_map.json`。",
        "- 评分：12 维 × 1–5 分；请在 `blind_scoring_sheet.csv` 填 `score`，并在 `rationale` 留下简短依据。",
        "- 评分锁定后，再运行聚合脚本完成解盲和 A/B 差值计算。",
        "",
        "## 评分维度与锚点",
        "",
        "| 维度 | 锚点 |",
        "|---|---|",
    ]
    for item in RUBRIC:
        lines.append(f"| {item['label']} ({item['key']}) | {item['anchor']} |")

    for case_id in sorted(samples_by_case):
        lines += ["", "---", "", f"# 用例：{case_id}", ""]
        case = cases.get(case_id)
        if case:
            lines += [
                f"**本章目标**：{case.data.get('chapter_goal', '')}",
                "",
                f"**用户额外要求**：{case.data.get('user_notes', '')}",
                "",
                f"**目标字数**：{case.data.get('target_chars', '')}",
                "",
            ]
        ordered = sorted(
            samples_by_case[case_id],
            key=lambda item: _blind_order_key(blind_map["run_id"], case_id, item["variant"]),
        )
        for sample in ordered:
            text = (run_path / sample["source_file"]).read_text(encoding="utf-8")
            lines += [
                f"## {case_id} · 样本 {sample['sample_id']}",
                "",
                f"（正文 {len(text)} 字）",
                "",
                "```text",
                text.strip(),
                "```",
                "",
            ]

    map_path = run_path / "blind_map.json"
    map_path.write_text(json.dumps(blind_map, ensure_ascii=False, indent=2), encoding="utf-8")

    sheet_path = _write_blind_sheet(
        blind_map["run_id"],
        blind_map["samples"],
        run_path / "blind_scoring_sheet.csv",
    )

    pack_path = run_path / "blind_scoring_pack.md"
    pack_path.write_text("\n".join(lines), encoding="utf-8")
    return {"pack": pack_path, "sheet": sheet_path, "map": map_path}


def _load_blind_map(map_path: str | Path) -> dict[str, Any]:
    path = Path(map_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"不支持的盲化映射版本: {data.get('schema_version')}")
    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("blind_map.json 缺少 samples")
    return data


def load_blind_scores(
    csv_path: str | Path,
    map_path: str | Path,
) -> list[dict[str, Any]]:
    """Read scored blind rows and restore the hidden variant labels."""
    blind_map = _load_blind_map(map_path)
    sample_lookup = {sample["sample_id"]: sample for sample in blind_map["samples"]}
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    with Path(csv_path).open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw_score = (row.get("score") or "").strip()
            if not raw_score:
                continue

            run_id = (row.get("run_id") or "").strip()
            if run_id != blind_map["run_id"]:
                raise ValueError(f"评分表 run_id 与 blind_map 不一致: {run_id!r}")

            sample_id = (row.get("sample_id") or "").strip()
            sample = sample_lookup.get(sample_id)
            if not sample:
                raise ValueError(f"评分表包含未知 sample_id: {sample_id!r}")
            case_id = (row.get("case_id") or "").strip()
            if case_id != sample["case_id"]:
                raise ValueError(
                    f"评分表 case_id 与 blind_map 不一致: {sample_id} -> {case_id!r}"
                )

            dimension = (row.get("dimension_key") or "").strip()
            if dimension not in RUBRIC_KEYS:
                raise ValueError(f"未知评分维度: {dimension!r}")
            key = (sample_id, dimension)
            if key in seen:
                raise ValueError(f"重复评分行: {sample_id}/{dimension}")
            seen.add(key)

            try:
                score = int(raw_score)
            except ValueError as exc:
                raise ValueError(
                    f"评分必须为整数 1–5: {sample_id}/{dimension}={raw_score!r}"
                ) from exc
            if not 1 <= score <= 5:
                raise ValueError(f"评分必须为 1–5: {sample_id}/{dimension}={score}")

            rows.append(
                {
                    "run_id": run_id,
                    "case_id": sample["case_id"],
                    "variant": sample["variant"],
                    "dimension": dimension,
                    "score": score,
                    "notes": (row.get("rationale") or "").strip(),
                    "sample_id": sample_id,
                }
            )
    return rows


def blind_score_status(
    csv_path: str | Path,
    map_path: str | Path,
) -> dict[str, Any]:
    """Return completeness for the frozen blind scoring grid."""
    blind_map = _load_blind_map(map_path)
    rows = load_blind_scores(csv_path, map_path)
    expected = {
        (sample["sample_id"], dimension)
        for sample in blind_map["samples"]
        for dimension in RUBRIC_KEYS
    }
    scored = {(row["sample_id"], row["dimension"]) for row in rows}
    missing = sorted(expected - scored)
    return {
        "run_id": blind_map["run_id"],
        "expected_rows": len(expected),
        "scored_rows": len(scored),
        "complete": not missing,
        "missing": [
            {"sample_id": sample_id, "dimension_key": dimension}
            for sample_id, dimension in missing
        ],
    }


def aggregate_blind_scores(
    csv_path: str | Path,
    map_path: str | Path,
) -> dict[str, Any]:
    """Require a complete blind grid, unblind it, then use the canonical aggregator."""
    status = blind_score_status(csv_path, map_path)
    if not status["complete"]:
        preview = ", ".join(
            f"{item['sample_id']}/{item['dimension_key']}" for item in status["missing"][:6]
        )
        more = len(status["missing"]) - min(6, len(status["missing"]))
        suffix = f" 等（另有 {more} 项）" if more else ""
        raise ValueError(
            f"盲化评分未完成：{status['scored_rows']}/{status['expected_rows']}；缺少 {preview}{suffix}"
        )
    rows = load_blind_scores(csv_path, map_path)
    summary = aggregate_scores(rows)
    summary["blind_scoring"] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": status["run_id"],
        "scored_rows": status["scored_rows"],
        "expected_rows": status["expected_rows"],
        "complete": True,
    }
    return summary
