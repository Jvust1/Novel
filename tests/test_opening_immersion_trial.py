"""Auditable, exact-excerpt blind-read preparation; not a claim of reader preference.

Checks the published Novel demonstration remains immutable and only permitted opening text
differs. Real participant ratings and model-caused uplift are out of scope.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "writing_demos/plugin-first-chapter-20261001"
TRIAL = DEMO / "opening-immersion-trial"


def test_opening_comparison_is_reversible_only_with_declared_patches():
    source_path = DEMO / "chapter-001.md"
    raw = source_path.read_bytes()
    record = json.loads((TRIAL / "trial-record.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(raw).hexdigest() == record["source"]["source_sha256"]
    source = raw.decode("utf-8")
    start_marker, end_marker = (record["source"][k] for k in ("start_marker", "end_marker"))
    assert source.count(start_marker) == source.count(end_marker) == 1
    start = source.index(start_marker)
    end = source.index(end_marker) + len(end_marker)
    baseline = source[start:end]
    assert (TRIAL / "reader/01.md").read_text(encoding="utf-8") == baseline
    edited = baseline
    for patch in record["patches"]:
        assert edited.count(patch["before"]) == 1, patch["reason"]
        edited = edited.replace(patch["before"], patch["after"], 1)
    assert (TRIAL / "reader/02.md").read_text(encoding="utf-8") == edited
    assert len(edited) > 0 and len(baseline) > 0 and edited != baseline
    assert source[:start] + edited + source[end:] != source
    assert source[end:].startswith('\n\n“找个包。”')
    for candidate in (baseline, edited):
        for marker in ('“里面的纸，你们看过没有？”', '六点十分的汽车票',
                       '“代领要物主确认。你拨一下他的电话。”', '五点五十。',
                       '明早七点到岗'):
            assert marker in candidate
        assert '外二底' not in candidate
        assert '桥下响了一声' not in candidate
    assert record["claims"]["independent_reader_ratings_collected"] is False
    assert record["claims"]["author_acceptance"] is None
    assert record["claims"]["canon_advanced"] is False


def test_blind_reader_files_do_not_leak_variant_identity():
    instructions = (TRIAL / "reader/rating-form.md").read_text(encoding="utf-8")
    assert "01 / 02 / 无明显差别" in instructions
    assert "先读" in instructions
    for name in ("01.md", "02.md"):
        sample = (TRIAL / "reader" / name).read_text(encoding="utf-8")
        assert sample.startswith(("那人来领工具包", "陶青脚边的旅行袋"))
        for forbidden in ("baseline", "candidate", "AI生成", "原稿：", "改稿："):
            assert forbidden not in sample
