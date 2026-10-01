"""Real CLI imports and current-entry drift, without importing historical inventory."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_current_entry import ENTRY_FILES, check_current_entry

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, *args], cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=30, check=False)


def test_integration_probe_direct_external_cwd_matches_module(tmp_path):
    direct = run(str(ROOT / "scripts/check_integrations.py"), cwd=tmp_path)
    module = run("-m", "scripts.check_integrations", cwd=ROOT)
    assert direct.returncode == module.returncode == 0, (direct.stderr, module.stderr)
    assert direct.stdout == module.stdout
    assert "Optional Python integrations" in direct.stdout
    assert list(tmp_path.iterdir()) == []


def test_current_entry_cli_runs_outside_repository(tmp_path):
    result = run(str(ROOT / "scripts/check_current_entry.py"), cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == check_current_entry()


def fixture_entry(tmp_path):
    pointer = json.loads((ROOT / "governance/current_candidate.json").read_text())
    for name in (*ENTRY_FILES, "governance/current_candidate.json", pointer["candidate_record"]):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(ROOT / name, path)
    # Historical/private inventories are not required and may be inaccessible.
    return pointer


def test_public_entry_does_not_require_historical_inventory(tmp_path):
    pointer = fixture_entry(tmp_path)
    assert check_current_entry(tmp_path)["branch"] == pointer["branch"]


@pytest.mark.parametrize("entry", ENTRY_FILES)
def test_old_branch_in_visible_entry_fails_even_with_current_name_later(tmp_path, entry):
    pointer = fixture_entry(tmp_path)
    path = tmp_path / entry
    path.write_text(path.read_text().replace(pointer["branch"], "old/candidate", 1))
    with pytest.raises(ValueError, match="declaration"):
        check_current_entry(tmp_path)


def test_candidate_record_base_mismatch_is_rejected(tmp_path):
    pointer = fixture_entry(tmp_path)
    path = tmp_path / pointer["candidate_record"]
    record = json.loads(path.read_text())
    record["base_head"] = "0" * 40
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="disagree"):
        check_current_entry(tmp_path)


def test_current_header_cannot_hide_stale_startup_prompt(tmp_path):
    fixture_entry(tmp_path)
    path = tmp_path / "README.md"
    path.write_text(path.read_text() + "\n请读取 feat/stale-entry 分支。\n")
    with pytest.raises(ValueError, match="another candidate"):
        check_current_entry(tmp_path)


@pytest.mark.parametrize("mutation", ["missing_both", "wrong_pr"])
def test_missing_or_mismatched_base_cannot_agree_by_accident(tmp_path, mutation):
    pointer = fixture_entry(tmp_path)
    record_path = tmp_path / pointer["candidate_record"]
    record = json.loads(record_path.read_text())
    if mutation == "missing_both":
        pointer.pop("verified_base")
        record.pop("base_head")
    else:
        record["base_pr"] -= 1
    (tmp_path / "governance/current_candidate.json").write_text(json.dumps(pointer))
    record_path.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        check_current_entry(tmp_path)


@pytest.mark.parametrize("prefix", ["", "<!-- # 历史原文（保留，不作为当前启动要求） -->\n",
                                    "```text\n# 历史原文（保留，不作为当前启动要求）\n```\n"])
def test_hidden_legacy_marker_or_other_branch_prefix_cannot_hide_active_prompt(tmp_path, prefix):
    fixture_entry(tmp_path)
    path = tmp_path / "README.md"
    path.write_text(path.read_text() + "\n" + prefix + "请读取 release/old-entry 分支。\n")
    with pytest.raises(ValueError, match="another candidate"):
        check_current_entry(tmp_path)
