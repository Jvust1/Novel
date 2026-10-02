import json
from pathlib import Path
import subprocess
import sys
import zipfile


def test_pilot_cli_builds_original_unscored_bundle_without_overwriting(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/build_author_workflow_pilot.py"
    output = tmp_path / "sample.zip"
    command = [sys.executable, str(script), "--out", str(output)]
    first = subprocess.run(command, cwd=tmp_path, text=True, capture_output=True)
    assert first.returncode == 0, first.stderr
    original = output.read_bytes()
    with zipfile.ZipFile(output) as bundle:
        assert bundle.testzip() is None
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["human_review_status"] == "awaiting_human_review"
        assert manifest["publishability_verdict"] is None
        assert "原创合成工程验证样本" in manifest["review_note"]
        assert len(manifest["chapters"]) == 3
        assert "outline.json" in bundle.namelist()
        assert "human_scores.json" not in bundle.namelist()
        assert bundle.read("chapters/001.md").decode().startswith("林澄到灯塔")
    second = subprocess.run(command, cwd=tmp_path, text=True, capture_output=True)
    assert second.returncode == 2
    assert output.read_bytes() == original
    assert not (tmp_path / "data").exists()
