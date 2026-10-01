from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

from ._vendor.boltons_atomic import atomic_save, sync_directory
from .storage_guard import project_lock, reject_links

_INTENT = ".extraction-transaction.json"
_RESERVED = {".store.lock", _INTENT}
_MAX_INTENT_BYTES = 64 * 1024 * 1024


class StorageIntegrityError(ValueError):
    """Stored data is incomplete or conflicts with a recoverable write intent."""


def _json(data: Any, *, indent: int | None = None) -> str:
    return json.dumps(data, ensure_ascii=False, indent=indent, allow_nan=False)


def _reject_constant(value: str):
    raise ValueError("nonfinite JSON constant refused: " + value)


def _loads(content: str) -> Any:
    value = json.loads(content, parse_constant=_reject_constant)
    _json(value).encode("utf-8")  # Also reject numeric overflow (1e999) and invalid Unicode.
    return value


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _file_digest(path: Path) -> str | None:
    return _digest(path.read_bytes()) if path.exists() else None


class ProjectStore:
    """Confined local storage with atomic files and cooperating-project locks.

    Path rules and stable summary ordering reconcile existing Novel PR16/PR13.
    Actual atomic publication uses the licensed boltons source port. This does
    not provide remote/Drive transactions or a hostile-directory sandbox.
    """

    def __init__(self, root: str | Path = "data"):
        self.root = Path(root).absolute()
        reject_links(self.root)
        self.root = self.root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def slugify(name: str) -> str:
        name = name.strip() or "novel"
        slug = re.sub(r"[^\w\-\u4e00-\u9fff]+", "-", name, flags=re.UNICODE).strip("-")
        slug = slug[:80] or "novel"
        if re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])", slug):
            slug = "_" + slug
        return slug

    def project_dir(self, name: str) -> Path:
        path = self.root / "projects" / self.slugify(name)
        reject_links(path)
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("项目目录越界")
        for child in ["chapters", "memory", "styles", "exports"]:
            target = path / child
            reject_links(target)
            target.mkdir(parents=True, exist_ok=True)
        return path

    def _path(self, project: str, relative: str, *, internal: bool = False) -> Path:
        # Adapted from Novel PR16's existing confined path boundary.
        if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
            raise ValueError("仅允许项目内相对路径")
        parts = PurePosixPath(relative)
        segments = relative.split("/")
        if parts.is_absolute() or any(part in {"", ".", ".."} for part in segments):
            raise ValueError("仅允许项目内相对路径")
        if any(len(part.encode("utf-8")) > 255 or "\0" in part for part in segments):
            raise ValueError("项目路径片段过长或无效")
        if any(part.endswith((".", " ")) or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part) for part in segments):
            raise ValueError("项目路径包含跨平台设备名或尾部别名")
        if not internal and segments[0].casefold() in _RESERVED:
            raise ValueError("内部锁与恢复记录不能通过内容 API 修改")
        root = self.project_dir(project)
        path = root / relative
        reject_links(path)
        if not path.resolve().is_relative_to(root.resolve()) or path.resolve() == root.resolve():
            raise ValueError("路径越界")
        return path

    @contextmanager
    def _guard(self, project: str):
        lock = self._path(project, ".store.lock", internal=True)
        with project_lock(lock):
            self._recover_extraction(project)
            yield

    def _write(self, path: Path, content: str, *, overwrite: bool = True) -> None:
        reject_links(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        reject_links(path)
        with atomic_save(path, overwrite=overwrite, file_perms=0o600) as stream:
            stream.write(content.encode("utf-8"))

    def write_json(self, project: str, relative: str, data: Any) -> Path:
        content = _json(data, indent=2)  # Validate fully before opening any output.
        path = self._path(project, relative)
        with self._guard(project):
            self._write(path, content)
        return path

    def read_json(self, project: str, relative: str, default: Any = None) -> Any:
        path = self._path(project, relative)
        with self._guard(project):
            if not path.exists():
                return default
            try:
                return _loads(path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeError) as exc:
                raise StorageIntegrityError("JSON 文件损坏，请保留原件并恢复或对账: " + relative) from exc

    def append_jsonl(self, project: str, relative: str, row: dict[str, Any]) -> Path:
        line = _json(row) + "\n"
        path = self._path(project, relative)
        with self._guard(project):
            existing = path.read_text(encoding="utf-8") if path.exists() else ""
            for item in existing.splitlines():
                if item.strip():
                    _loads(item)
            if existing and not existing.endswith("\n"):
                existing += "\n"
            self._write(path, existing + line)
        return path

    def write_chapter(self, project: str, chapter_id: str, text: str) -> Path:
        path = self._path(project, "chapters/" + self.slugify(chapter_id) + ".md")
        with self._guard(project):
            self._write(path, text.strip() + "\n")
        return path

    def all_chapter_texts(self, project: str) -> list[tuple[str, str]]:
        rows = []
        with self._guard(project):
            for path in sorted((self.project_dir(project) / "chapters").glob("*.md")):
                reject_links(path)
                rows.append((path.stem, path.read_text(encoding="utf-8")))
        return rows

    def recent_chapter_summaries(self, project: str, limit: int = 4) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return self.all_chapter_summaries(project)[-limit:]

    def _summaries(self, project: str) -> list[dict[str, Any]]:
        path = self._path(project, "memory/chapter_summaries.jsonl")
        if not path.exists():
            return []
        rows = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = _loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("summary row must be an object")
                    rows.append(row)
        except (ValueError, UnicodeError) as exc:
            raise StorageIntegrityError("章节摘要损坏，请保留原件并恢复或对账") from exc
        return rows

    def all_chapter_summaries(self, project: str) -> list[dict[str, Any]]:
        with self._guard(project):
            return self._summaries(project)

    def _recover_extraction(self, project: str) -> None:
        """Roll forward one explicit two-file intent under the stable project lock.

        This is a bounded extraction/summary recovery protocol, not a generic
        transaction engine. Validate ALL sources before publishing either file.
        """
        intent = self._path(project, _INTENT, internal=True)
        if not intent.exists():
            return
        try:
            if intent.stat().st_size > _MAX_INTENT_BYTES:
                raise ValueError("intent exceeds the supported recovery size")
            data = _loads(intent.read_text(encoding="utf-8"))
            if set(data) != {"version", "project", "files"} or type(data["version"]) is not int or data["version"] != 1 or data["project"] != self.slugify(project):
                raise ValueError("recovery identity differs")
            files = data["files"]
            if not isinstance(files, list) or len(files) != 2:
                raise ValueError("recovery requires exactly extraction and summary")
            if files[1]["path"] != "memory/chapter_summaries.jsonl" or not re.fullmatch(r"memory/extractions/[^/]+\.json", files[0]["path"]):
                raise ValueError("unsupported recovery targets")
            pending = []
            for item in files:
                if set(item) != {"path", "before_sha256", "after_sha256", "content"} or not isinstance(item["content"], str):
                    raise ValueError("invalid recovery record")
                content = item["content"].encode("utf-8")
                if _digest(content) != item["after_sha256"]:
                    raise ValueError("recovery content digest differs")
                path = self._path(project, item["path"])
                current = _file_digest(path)
                if current not in {item["before_sha256"], item["after_sha256"]}:
                    raise ValueError("a recovery target was independently changed")
                pending.append((path, item["content"], current != item["after_sha256"]))
            # Validate related content, not merely the strings/hashes.
            extraction = _loads(files[0]["content"])
            summaries = [_loads(line) for line in files[1]["content"].splitlines() if line.strip()]
            if not isinstance(extraction, dict) or any(not isinstance(row, dict) for row in summaries):
                raise ValueError("invalid extraction/summary shape")
            chapter_id = str(extraction.get("chapter_id") or "chapter").strip() or "chapter"
            matches = [row for row in summaries if str(row.get("chapter_id")) == chapter_id]
            expected = {"chapter_id": chapter_id, "chapter_title": extraction.get("chapter_title", ""), "summary": extraction.get("summary", "")}
            if len(matches) != 1 or matches[0] != expected or files[0]["path"] != f"memory/extractions/{self.slugify(chapter_id)}.json":
                raise ValueError("extraction and summary do not agree")
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise StorageIntegrityError("待恢复的抽取/摘要事务损坏或冲突，请保留原件并人工对账") from exc
        for path, content, needed in pending:
            if needed:
                self._write(path, content)
        for parent in {path.parent for path, _, _ in pending}:
            sync_directory(parent)
        intent.unlink()
        sync_directory(intent.parent)

    def save_extraction(self, project: str, extraction: dict[str, Any]) -> Path:
        """Persist extraction and stable summary through a recoverable intent."""
        chapter_id = str(extraction.get("chapter_id") or "chapter").strip() or "chapter"
        extraction_content = _json(extraction, indent=2)
        summary = {"chapter_id": chapter_id, "chapter_title": extraction.get("chapter_title", ""), "summary": extraction.get("summary", "")}
        extraction_path = self._path(project, f"memory/extractions/{self.slugify(chapter_id)}.json")
        summary_path = self._path(project, "memory/chapter_summaries.jsonl")
        with self._guard(project):
            if extraction_path.exists():
                previous = _loads(extraction_path.read_text(encoding="utf-8"))
                previous_id = str(previous.get("chapter_id") or "chapter").strip() or "chapter"
                if previous_id != chapter_id:
                    raise StorageIntegrityError("不同章节 ID 映射到同一文件名，请先更换稳定 ID")
            rows = self._summaries(project)
            for index, row in enumerate(rows):
                if str(row.get("chapter_id")) == chapter_id:
                    rows = rows[:index] + [summary] + [later for later in rows[index + 1:] if str(later.get("chapter_id")) != chapter_id]
                    break
            else:
                rows.append(summary)
            contents = [(extraction_path, extraction_content), (summary_path, "".join(_json(row) + "\n" for row in rows))]
            files = []
            root = self.project_dir(project)
            for path, content in contents:
                files.append({"path": path.relative_to(root).as_posix(), "before_sha256": _file_digest(path),
                              "after_sha256": _digest(content.encode("utf-8")), "content": content})
            if all(item["before_sha256"] == item["after_sha256"] for item in files):
                return summary_path
            intent = self._path(project, _INTENT, internal=True)
            serialized = _json({"version": 1, "project": self.slugify(project), "files": files})
            if len(serialized.encode("utf-8")) > _MAX_INTENT_BYTES:
                raise ValueError("抽取与摘要超过当前恢复事务大小上限；原文件未修改")
            self._write(intent, serialized, overwrite=False)
            self._recover_extraction(project)
        return summary_path

    def save_story_dna(self, project: str, chapter_id: str, story_dna: dict[str, Any]) -> Path:
        safe = self.slugify(chapter_id or "chapter")
        record = {"chapter_id": chapter_id, "story_dna": story_dna}
        return self.write_json(project, f"memory/story_dna/{safe}.json", record)

    def save_voice_dna(self, project: str, chapter_id: str, voice_dna: dict[str, Any]) -> Path:
        safe = self.slugify(chapter_id or "chapter")
        record = {"chapter_id": chapter_id, "voice_dna": voice_dna}
        return self.write_json(project, f"memory/voice_dna/{safe}.json", record)

    def _load_history(self, project: str, folder_name: str, field: str) -> list[dict[str, Any]]:
        rows = []
        folder = self._path(project, "memory/" + folder_name)
        with self._guard(project):
            for path in sorted(folder.glob("*.json")):
                reject_links(path)
                try:
                    row = _loads(path.read_text(encoding="utf-8"))
                    if not isinstance(row, dict) or not isinstance(row.get(field), dict):
                        raise ValueError("history entry has an unexpected shape")
                except (ValueError, UnicodeError) as exc:
                    raise StorageIntegrityError("历史记忆文件损坏，请保留原件并对账: " + path.name) from exc
                rows.append(row)
        return rows

    def load_voice_dna_history(self, project: str) -> list[dict[str, Any]]:
        return self._load_history(project, "voice_dna", "voice_dna")

    def save_longform_health(self, project: str, health: dict[str, Any]) -> Path:
        return self.write_json(project, "memory/longform_health.json", health)

    def load_longform_health(self, project: str) -> dict[str, Any]:
        return self.read_json(project, "memory/longform_health.json", default={})

    def save_chapter_analytics(self, project: str, chapter_id: str, analytics: dict[str, Any]) -> Path:
        safe = self.slugify(chapter_id or "chapter")
        record = {"chapter_id": chapter_id, "analytics": analytics}
        return self.write_json(project, f"memory/chapter_analytics/{safe}.json", record)

    def load_chapter_analytics_history(self, project: str) -> list[dict[str, Any]]:
        return self._load_history(project, "chapter_analytics", "analytics")

    def load_story_dna_history(self, project: str) -> list[dict[str, Any]]:
        return self._load_history(project, "story_dna", "story_dna")

    def load_story_state(self, project: str) -> dict[str, Any]:
        return self.read_json(
            project,
            "memory/story_state.json",
            default={"facts": [], "timeline": [], "foreshadowing": [], "open_threads": []},
        )

    def save_story_state(self, project: str, state: dict[str, Any]) -> Path:
        return self.write_json(project, "memory/story_state.json", state)
