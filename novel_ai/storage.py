from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class ProjectStore:
    """Local-first storage for manuscripts and evolving story memory."""

    def __init__(self, root: str | Path = "data"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def slugify(name: str) -> str:
        name = name.strip() or "novel"
        slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", name, flags=re.UNICODE).strip("-")
        return slug[:80] or "novel"

    def project_dir(self, name: str) -> Path:
        path = self.root / "projects" / self.slugify(name)
        for child in ["chapters", "memory", "styles", "exports"]:
            (path / child).mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, project: str, relative: str, data: Any) -> Path:
        path = self.project_dir(project) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def read_json(self, project: str, relative: str, default: Any = None) -> Any:
        path = self.project_dir(project) / relative
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def append_jsonl(self, project: str, relative: str, row: dict[str, Any]) -> Path:
        path = self.project_dir(project) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    def write_chapter(self, project: str, chapter_id: str, text: str) -> Path:
        safe_id = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", chapter_id).strip("-") or "chapter"
        path = self.project_dir(project) / "chapters" / f"{safe_id}.md"
        path.write_text(text.strip() + "\n", encoding="utf-8")
        return path

    def all_chapter_texts(self, project: str) -> list[tuple[str, str]]:
        chapter_dir = self.project_dir(project) / "chapters"
        rows: list[tuple[str, str]] = []
        for path in sorted(chapter_dir.glob("*.md")):
            rows.append((path.stem, path.read_text(encoding="utf-8")))
        return rows

    def recent_chapter_summaries(self, project: str, limit: int = 4) -> list[dict[str, Any]]:
        rows = self.all_chapter_summaries(project)
        return rows[-limit:]

    def all_chapter_summaries(self, project: str) -> list[dict[str, Any]]:
        path = self.project_dir(project) / "memory" / "chapter_summaries.jsonl"
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    def save_extraction(self, project: str, extraction: dict[str, Any]) -> Path:
        """Persist one chapter's memory extraction and append its summary row."""
        chapter_id = str(extraction.get("chapter_id") or "chapter").strip() or "chapter"
        self.write_json(project, f"memory/extractions/{self.slugify(chapter_id)}.json", extraction)
        summary = {
            "chapter_id": chapter_id,
            "chapter_title": extraction.get("chapter_title", ""),
            "summary": extraction.get("summary", ""),
        }
        rows = self.all_chapter_summaries(project)
        rows = [r for r in rows if str(r.get("chapter_id")) != chapter_id]
        rows.append(summary)
        path = self.project_dir(project) / "memory" / "chapter_summaries.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    def load_story_state(self, project: str) -> dict[str, Any]:
        return self.read_json(
            project,
            "memory/story_state.json",
            default={"facts": [], "timeline": [], "foreshadowing": [], "open_threads": []},
        )

    def save_story_state(self, project: str, state: dict[str, Any]) -> Path:
        return self.write_json(project, "memory/story_state.json", state)
