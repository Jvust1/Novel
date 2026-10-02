"""Synthetic Unicode JSON survives narrow redirected stdout/stderr encodings."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEXT = "合成探针：门外的风。 café العربية 😀\r\n下一行。\r\n"
STORY_ID = "synthetic-故事-😀"
ENCODINGS = ("ascii", "cp1252", "gbk", "utf-8")


def run_cli(cwd, encoding, *args):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONIOENCODING"] = encoding
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/story_state.py"), *map(str, args)],
        cwd=cwd, env=env, capture_output=True, timeout=30, check=False,
    )


@pytest.mark.parametrize("encoding", ENCODINGS)
def test_artifact_json_preserves_full_unicode_and_original_byte_hash(tmp_path, encoding):
    source = tmp_path / "合成-😀.txt"
    original = TEXT.encode("utf-8")
    source.write_bytes(original)
    result = run_cli(tmp_path, encoding, "artifact", source,
                     "--source-id", "合成-😀", "--revision", "版本一")
    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    output = json.loads(result.stdout.decode("ascii"))
    assert output["text"] == TEXT
    assert output["source"]["source_id"] == "合成-😀"
    assert output["source"]["revision"] == "版本一"
    assert output["source"]["location"] == str(source.absolute())
    assert output["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert source.read_bytes() == original
    assert list(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize("encoding", ENCODINGS)
def test_missing_unicode_path_is_one_json_error_without_traceback_or_writes(tmp_path, encoding):
    source = tmp_path / "不存在-😀.json"
    result = run_cli(tmp_path, encoding, "validate", source)
    assert result.returncode == 2, result.stderr
    assert result.stdout == b""
    output = json.loads(result.stderr.decode("ascii"))
    assert set(output) == {"error"}
    assert source.name in output["error"]
    assert b"Traceback" not in result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("encoding", ENCODINGS)
def test_create_validate_inspect_report_unicode_without_claiming_author_acceptance(tmp_path, encoding):
    source = tmp_path / "state.json"
    created = run_cli(tmp_path, encoding, "create", source,
                      "--story-id", STORY_ID, "--title", "合成标题 😀")
    assert created.returncode == 0, created.stderr
    receipt = json.loads(created.stdout.decode("ascii"))
    assert receipt["story_id"] == STORY_ID
    assert receipt["revision"] == 0
    assert receipt["phase"] == "planning"
    assert receipt["readback"].startswith("pending;")
    original = source.read_bytes()
    assert receipt["sha256"] == hashlib.sha256(original).hexdigest()
    checked = run_cli(tmp_path, encoding, "validate", source)
    assert checked.returncode == 0, checked.stderr
    validation = json.loads(checked.stdout.decode("ascii"))
    assert validation["story_id"] == STORY_ID
    assert validation["author_authenticated"] is False
    inspected = run_cli(tmp_path, encoding, "inspect", source,
                        "--story-id", STORY_ID, "--revision", "0",
                        "--sha256", receipt["sha256"])
    assert inspected.returncode == 0, inspected.stderr
    state = json.loads(inspected.stdout.decode("ascii"))["state"]
    assert state["story_id"] == STORY_ID
    assert state["title"] == "合成标题 😀"
    assert state["progress"]["plan_acceptance"] is None
    assert state["progress"]["chapter_acceptance"] is None
    assert state["progress"]["memory_acceptance"] is None
    assert source.read_bytes() == original
