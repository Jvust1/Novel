from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "chore/quality-gates-audit-20261002"


def test_current_candidate_governance_and_entry_refs_align():
    state = json.loads((ROOT / "governance/project_state.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "governance/artifact_manifest.json").read_text(encoding="utf-8"))
    assert state["repository"] == "Jvust1/Novel"
    assert state["quality_gate_candidate"]["branch"] == BRANCH
    assert state["quality_gate_candidate"]["base_pr"] == 59
    assert manifest["current_candidate"]["branch"] == BRANCH
    for path in ("README.md", "AGENTS.md", "docs/GPT_WRITING_ENTRY.md", "docs/HANDOFF.md"):
        assert BRANCH in (ROOT / path).read_text(encoding="utf-8")


def test_ci_has_dependency_static_compile_and_full_test_gates():
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "ruff==0.16.9" in requirements
    for required in (
        "python -m pip check",
        "ruff check app.py novel_ai scripts tests --select E9,F63,F7,F82",
        "ruff check app.py novel_ai scripts tests --output-format json --exit-zero",
        "python -m compileall app.py novel_ai scripts",
        "python scripts/check_integrations.py",
        "pytest -q",
    ):
        assert required in workflow


def test_quality_gate_documented_scope_exists():
    text = (ROOT / "docs/QUALITY_GATES_AUDIT.md").read_text(encoding="utf-8")
    assert "硬门" in text
    assert "维护性基线" in text
    assert "不安装全部可选依赖" in text
