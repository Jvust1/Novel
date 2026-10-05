from __future__ import annotations

import csv
import hashlib
import json
import io
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import ContextAssembler
from .engine import NovelEngine
from .models import Character, StoryBible
from .storage import ProjectStore
from .storage_guard import reject_links
from ._vendor.boltons_atomic import atomic_save

# E-000 固定评分维度：12 项，人工 1–5 分。
RUBRIC: list[dict[str, str]] = [
    {"key": "plot_pull", "label": "情节吸引力", "anchor": "1=完全不想读 3=勉强读下去 5=立刻想追更"},
    {"key": "causality", "label": "因果推进", "anchor": "1=剧情硬推 3=基本成立 5=选择与后果严密"},
    {"key": "motive", "label": "人物动机", "anchor": "1=工具人 3=大致可信 5=欲望/恐惧/代价完整"},
    {"key": "voice", "label": "人物声线", "anchor": "1=全员同声 3=主角有区分 5=对白遮住名字也能认人"},
    {"key": "continuity", "label": "连续性", "anchor": "1=知识边界/时间线穿帮 3=小瑕疵 5=完全自洽"},
    {"key": "pacing", "label": "节奏与信息释放", "anchor": "1=信息倾泻或拖沓 3=基本流畅 5=张弛与钩子精准"},
    {"key": "environment", "label": "环境功能", "anchor": "1=堆砌景物 3=偶有冗余 5=笔笔有用"},
    {"key": "psychology", "label": "心理描写", "anchor": "1=反复解释情绪 3=略多 5=克制有留白"},
    {"key": "ai_flavor", "label": "AI味/模板感", "anchor": "1=浓重 3=可察觉 5=几乎无感"},
    {"key": "style_dna", "label": "Style DNA 一致性", "anchor": "1=完全不符 3=部分符合 5=稳定贴合项目文风"},
    {"key": "end_hook", "label": "章末拉力", "anchor": "1=平淡收束 3=有点盼头 5=必须点开下一章"},
    {"key": "reuse_risk", "label": "参考复用风险", "anchor": "1=明显近似复用 3=局部存疑 5=干净"},
]

RUBRIC_KEYS = [item["key"] for item in RUBRIC]

VARIANTS = {
    "A_baseline": {
        "description": "v0.1 行为：仅 Bible + 人物卡 + 章纲 + 近章摘要，无长期记忆注入",
        "use_context_assembler": False,
    },
    "B_memory": {
        "description": "v0.2 行为：A 基础上注入 ContextAssembler 的 Canon/Active/Recall 长期记忆",
        "use_context_assembler": True,
    },
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class BenchmarkCase:
    case_id: str
    data: dict[str, Any]
    path: Path

    @property
    def bible(self) -> StoryBible:
        data = {k: v for k, v in self.data.items() if k in StoryBible.model_fields}
        return StoryBible.model_validate(data)

    @property
    def characters(self) -> list[Character]:
        return [Character.model_validate(c) for c in self.data.get("characters", [])]

    @property
    def pre_history(self) -> dict[str, Any]:
        return self.data.get("pre_history", {})


def load_benchmark(bench_dir: str | Path = "benchmarks") -> list[BenchmarkCase]:
    """Load frozen cases and verify each file hash against the manifest."""
    bench = Path(bench_dir)
    manifest = json.loads((bench / "benchmark_manifest.json").read_text(encoding="utf-8"))
    cases: list[BenchmarkCase] = []
    for entry in manifest["cases"]:
        path = bench / entry["file"]
        digest = sha256_file(path)
        if digest != entry["sha256"]:
            raise ValueError(
                f"基准用例 {entry['file']} 与冻结版本不一致：manifest={entry['sha256'][:12]}… actual={digest[:12]}…。"
                "冻结基准不得修改；如需新用例请新增文件并升级 manifest 版本。"
            )
        cases.append(BenchmarkCase(case_id=entry["case_id"], data=json.loads(path.read_text(encoding="utf-8")), path=path))
    return cases


def seed_store_from_case(case: BenchmarkCase, root: str | Path, project: str) -> ProjectStore:
    """Materialize a case's pre-history (summaries/facts/timeline/foreshadowing) into a store."""
    store = ProjectStore(root)
    pre = case.pre_history
    store.write_json(project, "memory/story_bible.json", case.bible.model_dump())
    store.save_story_state(
        project,
        {
            "facts": pre.get("facts", []),
            "timeline": pre.get("timeline", []),
            "foreshadowing": pre.get("foreshadowing", []),
            "open_threads": pre.get("open_threads", []),
        },
    )
    for row in pre.get("chapter_summaries", []):
        store.save_extraction(project, {"chapter_id": row["chapter_id"], "chapter_title": row.get("chapter_title", ""), "summary": row.get("summary", "")})
    return store


def run_case(
    engine: NovelEngine,
    case: BenchmarkCase,
    variant: str,
    store_root: str | Path,
    *,
    project: str = "bench",
    extra_notes: str = "",
) -> dict[str, Any]:
    """Run one frozen case under one variant. The only changed variable is the memory layer."""
    if variant not in VARIANTS:
        raise ValueError(f"未知变体: {variant}")
    config = VARIANTS[variant]
    store = seed_store_from_case(case, store_root, project)
    data = case.data
    characters = case.characters
    recent_limit = 4
    if config["use_context_assembler"]:
        ctx = ContextAssembler(store, project).assemble(recent_limit=recent_limit)
        recent, extra_context = ctx.recent_summaries, ctx.prompt_sections()
    else:
        recent, extra_context = store.recent_chapter_summaries(project, limit=recent_limit), ""

    result = engine.run(
        bible=case.bible,
        outline=data.get("outline", ""),
        chapter_goal=data.get("chapter_goal", ""),
        characters=characters,
        recent_summaries=recent,
        style=None,
        target_chars=int(data.get("target_chars", 3200)),
        user_notes=" ".join([data.get("user_notes", ""), extra_notes]).strip(),
        review=False,
        auto_repair=False,
        extra_context=extra_context,
    )
    final_text = result.draft
    return {
        "case_id": case.case_id,
        "variant": variant,
        "plan": result.plan.model_dump(),
        "text": final_text,
        "ai_flavor": result.ai_flavor,
        "extra_context_chars": len(extra_context),
        "recent_summary_count": len(recent),
    }


def run_benchmark(
    engine: NovelEngine,
    bench_dir: str | Path,
    out_root: str | Path,
    *,
    variants: list[str] | None = None,
    cases: list[str] | None = None,
    provider_note: str = "",
) -> Path:
    """Run all (case, variant) pairs into an immutable run folder. Returns the run dir."""
    variants = variants or list(VARIANTS)
    for variant in variants:
        if variant not in VARIANTS:
            raise ValueError(f"未知变体: {variant}")

    all_cases = load_benchmark(bench_dir)
    selected = [c for c in all_cases if not cases or c.case_id in cases]
    if not selected:
        raise ValueError("No benchmark cases matched; no evidence directory created")
    if len(variants) != len(set(variants)) or len({c.case_id for c in selected}) != len(selected):
        raise ValueError("benchmark cases and variants must be unique")
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", c.case_id) for c in selected):
        raise ValueError("benchmark case IDs must be safe stable filename identifiers")
    root = Path(out_root).absolute()
    reject_links(root)
    root.mkdir(parents=True, exist_ok=True)
    # Exclusive randomized directory allocation: same-second runs never share evidence.
    run_dir = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S-"), dir=root))
    run_id = run_dir.name

    run_record: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider_note": provider_note,
        "variants": {v: VARIANTS[v]["description"] for v in variants},
        "cases": [],
    }
    for case in selected:
        for variant in variants:
            record = run_case(engine, case, variant, store_root=run_dir / "_stores" / case.case_id)
            slug = f"{case.case_id}__{variant}"
            _write_new_evidence(run_dir / f"{slug}.txt", record.pop("text").encode("utf-8"))
            run_record["cases"].append(record)

    _write_new_evidence(run_dir / "run.json", json.dumps(run_record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    make_scoring_sheet(run_record, run_dir / "scoring_sheet.csv")
    return run_dir


def _write_new_evidence(path: Path, content: bytes) -> None:
    reject_links(path)
    with atomic_save(path, overwrite=False, file_perms=0o600) as stream:
        stream.write(content)


def make_scoring_sheet(run_record: dict[str, Any], path: str | Path) -> Path:
    """Emit a NEW blank scoring CSV; existing human scores are never overwritten."""
    path = Path(path)
    content = io.StringIO(newline="")
    writer = csv.writer(content)
    writer.writerow(["run_id", "case_id", "variant", "dimension_key", "dimension_label", "score", "notes"])
    for record in run_record["cases"]:
        for item in RUBRIC:
            writer.writerow([run_record["run_id"], record["case_id"], record["variant"],
                             item["key"], item["label"], "", item["anchor"]])
    _write_new_evidence(path, content.getvalue().encode("utf-8-sig"))
    return path


def load_scores(csv_path: str | Path) -> list[dict[str, Any]]:
    """Read a filled scoring sheet; only fully scored rows are returned."""
    rows: list[dict[str, Any]] = []
    with Path(csv_path).open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw = (row.get("score") or "").strip()
            if not raw:
                continue
            value = int(raw)
            if not 1 <= value <= 5:
                raise ValueError(f"评分必须为 1–5: {row['case_id']}/{row['variant']}/{row['dimension_key']}={value}")
            rows.append(
                {
                    "run_id": row["run_id"],
                    "case_id": row["case_id"],
                    "variant": row["variant"],
                    "dimension": row["dimension_key"],
                    "score": value,
                    "notes": (row.get("notes") or "").strip(),
                }
            )
    return rows


def aggregate_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate filled rows: per (case, variant) dimension means, overall means, and A/B deltas."""
    groups: dict[tuple[str, str], dict[str, list[int]]] = {}
    for row in rows:
        bucket = groups.setdefault((row["case_id"], row["variant"]), {})
        bucket.setdefault(row["dimension"], []).append(row["score"])

    summary: dict[str, Any] = {"by_group": {}, "variant_overall": {}, "deltas": {}}
    dim_totals: dict[str, list[float]] = {}
    for (case_id, variant), dims in sorted(groups.items()):
        means = {dim: sum(scores) / len(scores) for dim, scores in dims.items()}
        overall = sum(means.values()) / len(means) if means else 0.0
        summary["by_group"][f"{case_id}|{variant}"] = {
            "dimensions": {k: round(v, 3) for k, v in means.items()},
            "overall": round(overall, 3),
        }
        dim_totals.setdefault(variant, [])
        dim_totals[variant].append(overall)

    for variant, values in dim_totals.items():
        summary["variant_overall"][variant] = round(sum(values) / len(values), 3) if values else 0.0

    if {"A_baseline", "B_memory"} <= set(summary["variant_overall"]):
        a, b = summary["variant_overall"]["A_baseline"], summary["variant_overall"]["B_memory"]
        summary["deltas"]["B_minus_A"] = round(b - a, 3)
    return summary


def render_scoring_pack(run_dir: str | Path) -> Path:
    """Render a human-friendly side-by-side scoring pack (markdown) for one run.

    For each (case, variant) it includes the chapter goal, generation stats and
    the full text, plus the 12-dimension rubric with anchors. Read-only over
    the run directory; the pack lands next to run.json.
    """
    run_path = Path(run_dir)
    record = json.loads((run_path / "run.json").read_text(encoding="utf-8"))
    benchmark_dir = Path(__file__).resolve().parents[1] / "benchmarks"
    cases = {c.case_id: c for c in load_benchmark(benchmark_dir)} if (benchmark_dir / "benchmark_manifest.json").exists() else {}

    lines: list[str] = [
        f"# 评分包 · {record['run_id']}",
        "",
        f"- 模型：`{record.get('provider_note', '')}`",
        f"- 变体：A_baseline = 仅近章摘要；B_memory = 注入 Canon/Active/Recall 长期记忆（唯一变量）",
        "- 评分：12 维 × 1–5 分，填入同目录 `scoring_sheet.csv` 的 score 列。",
        "",
        "## 评分维度与锚点",
        "",
        "| 维度 | 锚点 |",
        "|---|---|",
    ]
    for item in RUBRIC:
        lines.append(f"| {item['label']} ({item['key']}) | {item['anchor']} |")

    by_case: dict[str, list[dict[str, Any]]] = {}
    for entry in record["cases"]:
        by_case.setdefault(entry["case_id"], []).append(entry)

    for case_id, entries in by_case.items():
        lines += ["", f"---", "", f"# 用例：{case_id}", ""]
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
        for entry in sorted(entries, key=lambda e: e["variant"]):
            text = (run_path / f"{entry['case_id']}__{entry['variant']}.txt").read_text(encoding="utf-8")
            lines += [
                f"## {case_id} · {entry['variant']}",
                "",
                f"（正文 {len(text)} 字；注入长期记忆 {entry['extra_context_chars']} 字）",
                "",
                "```text",
                text.strip(),
                "```",
                "",
            ]

    out = run_path / "scoring_pack.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
