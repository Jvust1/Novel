"""Check the public entry pointer without reading private artifact inventories."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY_FILES = ("README.md", "AGENTS.md", "docs/GPT_WRITING_ENTRY.md")


def _active_markdown(text: str) -> str:
    """Stop only at the real legacy heading, outside comments and fences."""
    visible = re.sub(r"<!--[\s\S]*?-->", "", text)
    fence = None
    active = []
    for line in visible.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            ticks, suffix = marker.groups()
            if fence is None:
                fence = (ticks[0], len(ticks))
            elif ticks[0] == fence[0] and len(ticks) >= fence[1] and not suffix.strip():
                fence = None
        if fence is None and line == "# 历史原文（保留，不作为当前启动要求）":
            break
        active.append(line)
    return "\n".join(active)


def check_current_entry(root: Path = ROOT) -> dict:
    pointer = json.loads((root / "governance/current_candidate.json").read_text(encoding="utf-8"))
    if pointer.get("schema") != "novel-public-current-candidate-v1" or pointer.get("repository") != "Jvust1/Novel":
        raise ValueError("invalid public candidate identity")
    branch = pointer.get("branch")
    if not isinstance(branch, str) or not re.fullmatch(r"[a-z0-9][a-z0-9/_-]+", branch):
        raise ValueError("missing exact candidate branch")
    if pointer.get("entry_files") != list(ENTRY_FILES):
        raise ValueError("current entry read order changed")
    candidate = pointer.get("candidate_record")
    if not isinstance(candidate, str) or not re.fullmatch(r"governance/[a-z_]+_candidate\.json", candidate):
        raise ValueError("candidate record must be an explicit public governance file")
    record = json.loads((root / candidate).read_text(encoding="utf-8"))
    base = pointer.get("verified_base")
    if (not isinstance(base, dict) or not isinstance(base.get("head"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", base["head"])
        or type(base.get("pr")) is not int or base["pr"] < 1):
        raise ValueError("verified base requires an exact commit and PR")
    if (record.get("branch") != branch or record.get("base_head") != base["head"]
        or type(record.get("base_pr")) is not int or record["base_pr"] != base["pr"]):
        raise ValueError("candidate record and current pointer disagree")
    for name in ENTRY_FILES:
        # Validate the human-visible first declaration, not a keyword anywhere
        # in an old example, comment or historical section.
        text = (root / name).read_text(encoding="utf-8")
        first = text.splitlines()[0]
        if first != f"当前候选：`{branch}`。公开工程入口以 [当前候选记录]({'governance/current_candidate.json' if '/' not in name else '../governance/current_candidate.json'}) 为准。":
            raise ValueError(f"current entry declaration does not match: {name}")
        active = _active_markdown(text)
        declared = set(re.findall(r"(?<![\w/])((?:feat|fix|chore)/[a-z0-9][a-z0-9/_-]*)", active))
        declared.update(re.findall(r"(?<![\w/])`?([a-z0-9][a-z0-9/_-]+)`?\s*分支", active))
        if declared != {branch}:
            raise ValueError(f"active entry contains another candidate branch: {name}")
    return {"branch": branch, "candidate_record": candidate, "checked_entry_files": list(ENTRY_FILES)}


def main() -> int:
    try:
        result = check_current_entry()
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"Current public entry check failed: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
