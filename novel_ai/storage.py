from __future__ import annotations

import json
import re
import os
import tempfile
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
        content = json.dumps(data, ensure_ascii=False, indent=2)
        # Replace one complete JSON document; a failed write keeps the prior file.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
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
        if limit <= 0:
            return []
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
        """Persist extraction, preserving an existing chapter's summary position."""
        chapter_id = str(extraction.get("chapter_id") or "chapter").strip() or "chapter"
        self.write_json(project, f"memory/extractions/{self.slugify(chapter_id)}.json", extraction)
        summary = {
            "chapter_id": chapter_id,
            "chapter_title": extraction.get("chapter_title", ""),
            "summary": extraction.get("summary", ""),
        }
        rows = self.all_chapter_summaries(project)
        for index, row in enumerate(rows):
            if str(row.get("chapter_id")) == chapter_id:
                rows = rows[:index] + [summary] + [
                    later for later in rows[index + 1:]
                    if str(later.get("chapter_id")) != chapter_id
                ]
                break
        else:
            rows.append(summary)
        path = self.project_dir(project) / "memory" / "chapter_summaries.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path

    def save_story_dna(self, project: str, chapter_id: str, story_dna: dict[str, Any]) -> Path:
        safe = self.slugify(chapter_id or "chapter")
        record = {"chapter_id": chapter_id, "story_dna": story_dna}
        return self.write_json(project, f"memory/story_dna/{safe}.json", record)

    def save_voice_dna(self, project: str, chapter_id: str, voice_dna: dict[str, Any]) -> Path:
        safe = self.slugify(chapter_id or "chapter")
        record = {"chapter_id": chapter_id, "voice_dna": voice_dna}
        return self.write_json(project, f"memory/voice_dna/{safe}.json", record)

    def load_voice_dna_history(self, project: str) -> list[dict[str, Any]]:
        folder = self.project_dir(project) / "memory" / "voice_dna"
        rows: list[dict[str, Any]] = []
        for path in sorted(folder.glob("*.json")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(row, dict) and isinstance(row.get("voice_dna"), dict):
                    rows.append(row)
            except (OSError, json.JSONDecodeError):
                continue
        return rows

    def save_longform_health(self, project: str, health: dict[str, Any]) -> Path:
        return self.write_json(project, "memory/longform_health.json", health)

    def load_longform_health(self, project: str) -> dict[str, Any]:
        return self.read_json(project, "memory/longform_health.json", default={})

    def save_chapter_analytics(self, project: str, chapter_id: str, analytics: dict[str, Any]) -> Path:
        safe = self.slugify(chapter_id or "chapter")
        record = {"chapter_id": chapter_id, "analytics": analytics}
        return self.write_json(project, f"memory/chapter_analytics/{safe}.json", record)

    def load_chapter_analytics_history(self, project: str) -> list[dict[str, Any]]:
        folder = self.project_dir(project) / "memory" / "chapter_analytics"
        rows: list[dict[str, Any]] = []
        for path in sorted(folder.glob("*.json")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(row, dict) and isinstance(row.get("analytics"), dict):
                    rows.append(row)
            except (OSError, json.JSONDecodeError):
                continue
        return rows

    def load_story_dna_history(self, project: str) -> list[dict[str, Any]]:
        folder = self.project_dir(project) / "memory" / "story_dna"
        rows: list[dict[str, Any]] = []
        for path in sorted(folder.glob("*.json")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(row, dict) and isinstance(row.get("story_dna"), dict):
                    rows.append(row)
            except (OSError, json.JSONDecodeError):
                continue
        return rows

    def load_story_state(self, project: str) -> dict[str, Any]:
        return self.read_json(
            project,
            "memory/story_state.json",
            default={"facts": [], "timeline": [], "foreshadowing": [], "open_threads": []},
        )

    def save_story_state(self, project: str, state: dict[str, Any]) -> Path:
        return self.write_json(project, "memory/story_state.json", state)
