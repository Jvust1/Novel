from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence


@dataclass(frozen=True)
class BookSkillRun:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def vendored_book_to_skill_root(repo_root: str | Path | None = None) -> Path:
    root = Path(repo_root or Path(__file__).resolve().parents[1])
    path = root / "vendor" / "book-to-skill"
    if not (path / "book_to_skill" / "__main__.py").exists():
        raise FileNotFoundError(
            "vendor/book-to-skill 未初始化。请先运行 git submodule update --init --recursive"
        )
    return path


def convert_documents_to_skill(
    inputs: Sequence[str | Path],
    *,
    skill_name: str | None = None,
    repo_root: str | Path | None = None,
    timeout: int = 1800,
) -> BookSkillRun:
    """Run the pinned book-to-skill source against local user-provided documents.

    The input documents stay local. Novel does not copy them into GitHub.
    BOOK_TO_SKILL_SCOPE=project asks the converter to use a project-local skill root.
    """
    if not inputs:
        raise ValueError("至少需要一个输入文档或目录")

    root = Path(repo_root or Path(__file__).resolve().parents[1]).resolve()
    vendor = vendored_book_to_skill_root(root)
    resolved = [str(Path(p).expanduser().resolve()) for p in inputs]
    for p in resolved:
        if not Path(p).exists():
            raise FileNotFoundError(p)

    cmd = [sys.executable, "-m", "book_to_skill", *resolved]
    if skill_name:
        cmd.append(skill_name)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(vendor) + os.pathsep + env.get("PYTHONPATH", "")
    env["BOOK_TO_SKILL_SCOPE"] = "project"
    proc = subprocess.run(
        cmd,
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return BookSkillRun(cmd, proc.returncode, proc.stdout, proc.stderr)
