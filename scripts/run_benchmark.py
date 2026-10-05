"""Run the frozen A/B benchmark.

Usage (from repo root):

    set NOVEL_BASE_URL=...      # OpenAI-compatible endpoint
    set NOVEL_MODEL=...         # model name
    set NOVEL_API_KEY=...       # optional; never written to disk

    python scripts/run_benchmark.py [--variants A_baseline B_memory] [--cases urban_dispute]

Results go to runs/<run_id>/ with chapter texts, run.json and a blank scoring
sheet. The API key is read from the environment and never persisted.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from novel_ai.engine import NovelEngine  # noqa: E402
from novel_ai.eval import run_benchmark  # noqa: E402
from novel_ai.provider import OpenAICompatibleProvider, ProviderConfig  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen Novel A/B benchmark")
    parser.add_argument("--benchmarks", default="benchmarks")
    parser.add_argument("--out", default="runs")
    parser.add_argument("--variants", nargs="*", default=None)
    parser.add_argument("--cases", nargs="*", default=None)
    args = parser.parse_args()

    base_url = os.environ.get("NOVEL_BASE_URL", "").strip()
    model = os.environ.get("NOVEL_MODEL", "").strip()
    api_key = os.environ.get("NOVEL_API_KEY", "").strip()
    if not base_url or not model:
        print("请先设置环境变量 NOVEL_BASE_URL 和 NOVEL_MODEL（API key 可选，密钥不会写入文件）。", file=sys.stderr)
        return 2

    engine = NovelEngine(OpenAICompatibleProvider(ProviderConfig(base_url=base_url, model=model, api_key=api_key)))
    note = f"model={model}"
    run_dir = run_benchmark(
        engine,
        args.benchmarks,
        args.out,
        variants=args.variants,
        cases=args.cases,
        provider_note=note,
    )
    print(f"完成。运行目录：{run_dir}")
    print(f"评分表（请人工填写 1–5 分）：{run_dir / 'scoring_sheet.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
