from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from novel_ai.reference_evidence import build_reference_evidence

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_reference_pack.py"


def source(name: str, text: str, encoding: str = "utf-8"):
    return (name, text.encode(encoding), None if encoding == "utf-8" else encoding)


def test_evidence_is_bounded_lexical_mmr_and_stable():
    sources = [
        source(
            "a.txt",
            "第一章 夜班电台\n\n夜班电台在雨里响起，周宁记下门牌。"
            "\n\n第二章 旧账本\n\n旧账本压在抽屉底，没人提电台。",
        ),
        source(
            "b.md",
            "# 第一章\n\n夜班电台的灯亮着，门外没有脚印。"
            "\n\n# 第二章\n\n河堤上的风吹散了纸片。",
        ),
    ]
    first = build_reference_evidence(
        sources, "夜班 电台", top_n=3, chunk_chars=80, max_excerpt_chars=40
    )
    second = build_reference_evidence(
        list(reversed(sources)), "夜班 电台", top_n=3, chunk_chars=80, max_excerpt_chars=40
    )
    assert first == second
    assert first["schema"] == "novel-reference-evidence-v1"
    assert first["offset_basis"] == "sanitized-extracted-unicode-codepoints"
    assert 0 < len(first["matches"]) <= 3
    assert all(0 < row["end"] - row["start"] <= 40 for row in first["matches"])
    assert all(row["excerpt"] for row in first["matches"])
    clean = {"a.txt": "第一章 夜班电台\n\n夜班电台在雨里响起，周宁记下门牌。\n\n第二章 旧账本\n\n旧账本压在抽屉底，没人提电台。", "b.md": "# 第一章\n\n夜班电台的灯亮着，门外没有脚印。\n\n# 第二章\n\n河堤上的风吹散了纸片。"}\n    assert all(row["excerpt"] == clean[row["source_filename"]][row["start"]:row["end"]] for row in first["matches"])
    assert [row["id"] for row in first["matches"]] == sorted(
        [row["id"] for row in first["matches"]], key=lambda value: first["matches"][
            [item["id"] for item in first["matches"]].index(value)
        ]
    )
    assert all(row["source_filename"] in {"a.txt", "b.md"} for row in first["matches"])
    assert all(row["backend"] and "encoding" in row for row in first["matches"])
    assert "河堤上的风吹散了纸片" not in "\n".join(row["excerpt"] for row in first["matches"])
    assert all("raw_source_sha256" in row and "extracted_text_sha256" in row for row in first["sources"])


def test_offsets_hashes_and_controls_use_extracted_clean_text():
    raw = "第一章\n\n零\u200b宽字符 夜班电台。".encode("utf-8")
    result = build_reference_evidence(
        [("unicode.txt", raw, None)], "夜班电台", top_n=1, chunk_chars=80, max_excerpt_chars=80
    )
    src = result["sources"][0]
    assert src["raw_source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert src["extracted_text_sha256"] == hashlib.sha256("第一章\n\n零宽字符 夜班电台。".encode()).hexdigest()
    row = result["matches"][0]
    assert "\u200b" not in row["excerpt"]
    assert row["excerpt"] == "第一章\n\n零宽字符 夜班电台。"[row["start"]:row["end"]]
    assert row["excerpt_sha256"] == hashlib.sha256(row["excerpt"].encode()).hexdigest()


def test_empty_and_missing_queries_are_fail_closed():
    with pytest.raises(ValueError, match="query"):
        build_reference_evidence([source("a.txt", "正文")], "   ")
    result = build_reference_evidence([source("a.txt", "正文")], "不存在的词", top_n=3)
    assert result["matches"] == []


def test_bounds_and_bad_input_are_rejected():
    with pytest.raises(ValueError):
        build_reference_evidence([source("a.txt", "正文")], "正文", top_n=0)
    with pytest.raises(ValueError):
        build_reference_evidence([source("a.txt", "正文")], "正文", max_excerpt_chars=0)
    with pytest.raises(ValueError):
        build_reference_evidence([("a.txt", b"\xff", "utf-8")], "正文")
    with pytest.raises(ValueError):
        build_reference_evidence([("a.txt", "正文".encode("utf-8"), None)], "正文", chunk_chars=10_000_000)


def cli(tmp_path, *args):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def test_cli_roundtrip_is_local_atomic_and_keeps_inputs_and_legacy_default(tmp_path):
    text = "第一章 夜班电台\n\n夜班电台在雨里响起。"
    source_path = tmp_path / "one.txt"
    source_path.write_bytes(text.encode())
    old = source_path.read_bytes()
    pack = tmp_path / "pack.json"
    evidence = tmp_path / "private" / "evidence.json"
    run = cli(
        tmp_path,
        source_path,
        "--out",
        pack,
        "--query",
        "夜班电台",
        "--evidence-out",
        evidence,
        "--top-n",
        "2",
    )
    assert run.returncode == 0, run.stderr
    assert source_path.read_bytes() == old
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["matches"]
    assert pack.exists()
    assert not any(p.suffix == ".tmp" for p in evidence.parent.iterdir())

    legacy = tmp_path / "legacy.json"
    legacy_run = cli(tmp_path, source_path, "--out", legacy)
    assert legacy_run.returncode == 0, legacy_run.stderr
    assert legacy.exists()
    assert not (tmp_path / "reference_evidence.json").exists()


def test_cli_requires_query_and_output_together_and_rejects_collisions(tmp_path):
    source_path = tmp_path / "one.txt"
    source_path.write_text("夜班电台", encoding="utf-8")
    pack = tmp_path / "pack.json"
    for args in (
        (source_path, "--evidence-out", tmp_path / "e.json"),
        (source_path, "--query", "夜班"),
    ):
        run = cli(tmp_path, *args)
        assert run.returncode == 2
        assert not (tmp_path / "e.json").exists()

    same = cli(
        tmp_path,
        source_path,
        "--out",
        pack,
        "--query",
        "夜班",
        "--evidence-out",
        source_path,
    )
    assert same.returncode == 2
    assert source_path.read_text(encoding="utf-8") == "夜班电台"

    existing = tmp_path / "existing.json"
    existing.write_text("complete", encoding="utf-8")
    rejected = cli(
        tmp_path,
        source_path,
        "--query",
        "夜班",
        "--evidence-out",
        existing,
    )
    assert rejected.returncode == 2
    assert existing.read_text(encoding="utf-8") == "complete"


def test_cli_rejects_directory_and_does_not_leave_manifest(tmp_path):
    directory = tmp_path / "refs"
    directory.mkdir()
    evidence = tmp_path / "evidence.json"
    run = cli(
        tmp_path,
        directory,
        "--query",
        "夜班",
        "--evidence-out",
        evidence,
    )
    assert run.returncode == 2
    assert not evidence.exists()
    assert not (tmp_path / "reference_pack.json").exists()


def test_real_optional_html_path_is_exercised_when_installed(tmp_path):
    pytest.importorskip("trafilatura")
    html = tmp_path / "reference.html"
    html.write_text(
        "<html><body><h1>第一章</h1><p>夜班电台的正文。</p></body></html>",
        encoding="utf-8",
    )
    output = tmp_path / "evidence.json"
    run = cli(
        tmp_path,
        html,
        "--query",
        "夜班电台",
        "--evidence-out",
        output,
    )
    assert run.returncode == 0, run.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["matches"][0]["backend"] == "trafilatura"
