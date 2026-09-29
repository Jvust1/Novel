import json
import csv
import subprocess
import sys
from pathlib import Path

import pytest

from novel_ai.market_eval import MarketChapter, MarketCorpus
from novel_ai.release_pack import MarketProfile, build_release_pack, load_release_pack, save_release_pack


def make_corpus():
    return MarketCorpus(
        project="novel",
        stage="opening_3",
        chapters=[
            MarketChapter(number=i, title=f"第{i}章", text=f"章节{i}正文")
            for i in range(1, 4)
        ],
    )


def make_profile():
    return MarketProfile(
        genre="都市悬疑",
        audience="喜欢快节奏悬疑的成年读者",
        tone="冷峻、克制",
        comparable_tags=["悬疑", "都市", "调查"],
    )


def test_release_pack_binds_metadata_to_corpus_without_text(tmp_path):
    corpus = make_corpus()
    pack = build_release_pack(
        corpus,
        make_profile(),
        title="夜班回声",
        one_line_hook="每晚接到死者电话的值班员，必须先找出下一个来电者。",
        short_blurb="一通深夜电话，把旧案和新的失踪案连在一起。",
        tags=["悬疑", "都市"],
    )
    assert pack.chapter_count == 3
    assert pack.corpus_sha256 == corpus.fingerprint()
    serialized = json.dumps(pack.model_dump(), ensure_ascii=False)
    assert "章节1正文" not in serialized

    path = save_release_pack(pack, tmp_path / "release.json")
    loaded = load_release_pack(path)
    assert loaded.title == "夜班回声"
    assert loaded.source_stage == "opening_3"


def test_release_pack_requires_explicit_copy_and_market_fields():
    with pytest.raises(ValueError, match="genre 和 audience"):
        MarketProfile(genre="", audience="")
    with pytest.raises(ValueError, match="one_line_hook"):
        build_release_pack(
            make_corpus(),
            make_profile(),
            title="标题",
            one_line_hook="",
            short_blurb="简介",
        )


def test_profile_tags_and_pack_tags_are_deduplicated_or_rejected():
    with pytest.raises(ValueError, match="不得重复"):
        MarketProfile(genre="都市", audience="读者", comparable_tags=["悬疑", "悬疑"])
    pack = build_release_pack(
        make_corpus(),
        make_profile(),
        title="标题",
        one_line_hook="钩子",
        short_blurb="简介",
        tags=["悬疑", "悬疑", "都市"],
    )
    assert pack.tags == ["悬疑", "都市"]


def test_release_pack_cli_builds_reviewable_json(tmp_path):
    corpus = make_corpus()
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(corpus.model_dump_json(), encoding="utf-8")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "profile": make_profile().model_dump(),
                "title": "夜班回声",
                "one_line_hook": "一通电话指向下一场失踪。",
                "short_blurb": "旧案与新案在夜班电话中交汇。",
                "tags": ["悬疑", "都市"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "release_pack.json"
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "build_release_pack.py"),
            str(corpus_path),
            str(metadata_path),
            "--out",
            str(output_path),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Wrote" in result.stdout
    exported = json.loads(output_path.read_text(encoding="utf-8"))
    assert exported["chapter_count"] == 3
    assert exported["source_stage"] == "opening_3"
    assert "章节1正文" not in output_path.read_text(encoding="utf-8")


def release_metadata():
    return {
        "profile": make_profile().model_dump(),
        "title": "夜班回声",
        "one_line_hook": "一通电话指向下一场失踪。",
        "short_blurb": "旧案与新案在夜班电话中交汇。",
        "tags": ["悬疑", "都市"],
    }


def write_cli_inputs(tmp_path):
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(make_corpus().model_dump_json(), encoding="utf-8")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(release_metadata()), encoding="utf-8")
    return corpus_path, metadata_path


def run_script(script, *args, cwd):
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / script)]
    return subprocess.run(
        [*command, *map(str, args)], cwd=cwd, capture_output=True, text=True,
    )


def test_saving_pack_preserves_existing_file(tmp_path):
    pack = build_release_pack(make_corpus(), make_profile(), title="标题", one_line_hook="钩子", short_blurb="简介")
    output = tmp_path / "release.json"
    original = b'{"previous": "review"}\n'
    output.write_bytes(original)
    with pytest.raises(FileExistsError):
        save_release_pack(pack, output)
    assert output.read_bytes() == original


@pytest.mark.parametrize("target", ["corpus", "metadata", "default_output"])
def test_cli_preserves_inputs_and_existing_pack(tmp_path, target):
    corpus_path, metadata_path = write_cli_inputs(tmp_path)
    output = tmp_path / "release_pack.json"
    output.write_text('{"previous": true}', encoding="utf-8")
    paths = {"corpus": corpus_path, "metadata": metadata_path, "default_output": output}
    originals = {name: path.read_bytes() for name, path in paths.items()}
    output_args = [] if target == "default_output" else ["--out", paths[target]]
    result = run_script("build_release_pack.py", corpus_path, metadata_path, *output_args, cwd=tmp_path)
    assert result.returncode == 2
    assert "已存在" in result.stderr
    assert "Traceback" not in result.stderr
    assert {name: path.read_bytes() for name, path in paths.items()} == originals


@pytest.mark.parametrize("field", ["tags", "content_warnings", "manual_checks"])
def test_builder_rejects_string_for_list_fields(field):
    with pytest.raises(ValueError, match=field):
        build_release_pack(
            make_corpus(), make_profile(), title="标题", one_line_hook="钩子", short_blurb="简介",
            **{field: "不应拆成单个字符"},
        )


@pytest.mark.parametrize(
    "bad_metadata, field",
    [
        ([], "元数据"),
        ({}, "profile"),
        ({**release_metadata(), "tags": "悬疑"}, "tags"),
        ({**release_metadata(), "content_warnings": [7]}, "content_warnings"),
        ({**release_metadata(), "manual_checks": None}, "manual_checks"),
    ],
)
def test_cli_rejects_invalid_metadata_without_output(tmp_path, bad_metadata, field):
    corpus_path, metadata_path = write_cli_inputs(tmp_path)
    metadata_path.write_text(json.dumps(bad_metadata), encoding="utf-8")
    output = tmp_path / "release.json"
    result = run_script("build_release_pack.py", corpus_path, metadata_path, "--out", output, cwd=tmp_path)
    assert result.returncode == 2
    assert field in result.stderr
    assert "Traceback" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("bad_input", ["missing_corpus", "broken_metadata"])
def test_cli_reports_unreadable_input_without_traceback(tmp_path, bad_input):
    corpus_path, metadata_path = write_cli_inputs(tmp_path)
    if bad_input == "missing_corpus":
        corpus_path.unlink()
    else:
        metadata_path.write_text('{"title":', encoding="utf-8")
    output = tmp_path / "release.json"
    result = run_script("build_release_pack.py", corpus_path, metadata_path, "--out", output, cwd=tmp_path)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    assert not output.exists()


@pytest.mark.parametrize("stage, count", [("unknown", 3), ("retention_20", 3), ("opening_3", 20)])
def test_loaded_pack_rejects_invalid_stage_or_chapter_count(tmp_path, stage, count):
    pack = build_release_pack(make_corpus(), make_profile(), title="标题", one_line_hook="钩子", short_blurb="简介")
    data = pack.model_dump()
    data.update(source_stage=stage, chapter_count=count)
    path = tmp_path / "release.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="source_stage|chapter_count"):
        load_release_pack(path)


@pytest.mark.parametrize("stage, count", [("opening_3", 3), ("retention_20", 20)])
def test_review_and_release_clis_share_corpus_fingerprint(tmp_path, stage, count):
    corpus_path, metadata_path = write_cli_inputs(tmp_path)
    corpus = MarketCorpus(
        project="integration-test", stage=stage,
        chapters=[MarketChapter(number=i, text=f"只用于测试的正文{i}") for i in range(1, count + 1)],
    )
    corpus_path.write_text(corpus.model_dump_json(), encoding="utf-8")
    sheet = tmp_path / "scores.csv"
    created = run_script("market_review.py", corpus_path, "--sheet", sheet, cwd=tmp_path)
    assert created.returncode == 0, created.stderr
    with sheet.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    for row in rows:
        row.update(reviewer_id="test-reviewer", score="3")
    with sheet.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    summary_path = tmp_path / "summary.json"
    reviewed = run_script("market_review.py", corpus_path, "--sheet", sheet, "--aggregate", "--out", summary_path, cwd=tmp_path)
    assert reviewed.returncode == 0, reviewed.stderr
    output = tmp_path / "release.json"
    built = run_script("build_release_pack.py", corpus_path, metadata_path, "--out", output, cwd=tmp_path)
    assert built.returncode == 0, built.stderr
    pack, summary = load_release_pack(output), json.loads(summary_path.read_text(encoding="utf-8"))
    assert pack.corpus_sha256 == summary["corpus_sha256"] == corpus.fingerprint()
    assert pack.source_stage == summary["stage"] == stage
    assert pack.chapter_count == count
    assert summary["publishability_verdict"] is None
    assert "只用于测试的正文" not in output.read_text(encoding="utf-8")
