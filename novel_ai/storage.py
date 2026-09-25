from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

_LOCK = threading.RLock()
_MAX_ARCHIVE = 100 * 1024 * 1024


def atomic_write(path: Path, text: str) -> None:
    """A failed replacement must leave the previous complete file readable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.novel-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ProjectStore:
    """Local manuscripts: confined paths, atomic writes and additive revisions."""

    def __init__(self, root: str | Path = 'data'):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def slugify(name: str) -> str:
        name = name.strip() or 'novel'
        slug = re.sub(r'[^\w\-\u4e00-\u9fff]+', '-', name, flags=re.UNICODE).strip('-')
        slug = slug[:80] or 'novel'
        if re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])', slug):
            slug = '_' + slug
        return slug

    def project_dir(self, name: str) -> Path:
        path = self.root / 'projects' / self.slugify(name)
        if not path.resolve().is_relative_to(self.root):
            raise ValueError('项目目录越界')
        for child in ['chapters', 'memory', 'styles', 'exports']:
            target = path / child
            if not target.resolve().is_relative_to(path.resolve()):
                raise ValueError('项目目录包含越界链接')
            target.mkdir(parents=True, exist_ok=True)
        return path

    def _path(self, project: str, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
            raise ValueError('仅允许项目内相对路径')
        parts = PurePosixPath(relative)
        if parts.is_absolute() or '..' in parts.parts:
            raise ValueError('仅允许项目内相对路径')
        root = self.project_dir(project).resolve()
        path = root / relative
        if not path.resolve().is_relative_to(root) or path.resolve() == root:
            raise ValueError('路径越界')
        return path

    def write_json(self, project: str, relative: str, data: Any) -> Path:
        path = self._path(project, relative)
        value = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
        with _LOCK:
            atomic_write(path, value)
        return path

    def read_json(self, project: str, relative: str, default: Any = None) -> Any:
        path = self._path(project, relative)
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding='utf-8'))

    def append_jsonl(self, project: str, relative: str, row: dict[str, Any]) -> Path:
        path = self._path(project, relative)
        with _LOCK:
            existing = path.read_text(encoding='utf-8') if path.exists() else ''
            atomic_write(path, existing + json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
        return path

    def write_chapter(self, project: str, chapter_id: str, text: str) -> Path:
        path = self._path(project, f'chapters/{self.slugify(chapter_id)}.md')
        value = text.strip() + '\n'
        with _LOCK:
            if path.exists():
                previous = path.read_text(encoding='utf-8')
                if previous == value:
                    return path
                digest = hashlib.sha256(previous.encode()).hexdigest()
                revision = self._path(project, f'chapters/history/{path.stem}/{digest}.md')
                if not revision.exists():
                    atomic_write(revision, previous)
            atomic_write(path, value)
        return path

    def recent_chapter_summaries(self, project: str, limit: int = 4) -> list[dict[str, Any]]:
        if type(limit) is not int or limit < 0:
            raise ValueError('摘要条数应为非负整数')
        return self.all_chapter_summaries(project)[-limit:] if limit else []

    def all_chapter_summaries(self, project: str) -> list[dict[str, Any]]:
        path = self._path(project, 'memory/chapter_summaries.jsonl')
        if not path.exists():
            return []
        rows: dict[str, dict[str, Any]] = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                row = json.loads(line)
                rows[str(row.get('chapter_id', 'chapter'))] = row
        return list(rows.values())

    def save_extraction(self, project: str, extraction: dict[str, Any]) -> Path:
        """Replace the summary in its original slot; never move old chapters last."""
        chapter_id = str(extraction.get('chapter_id') or 'chapter').strip() or 'chapter'
        with _LOCK:
            self.write_json(project, f'memory/extractions/{self.slugify(chapter_id)}.json', extraction)
            rows = {str(r.get('chapter_id')): r for r in self.all_chapter_summaries(project)}
            rows[chapter_id] = {k: extraction.get(k, '') for k in ('chapter_id', 'chapter_title', 'summary')}
            rows[chapter_id]['chapter_id'] = chapter_id
            path = self._path(project, 'memory/chapter_summaries.jsonl')
            atomic_write(path, ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows.values()))
        return path

    def load_story_state(self, project: str) -> dict[str, Any]:
        return self.read_json(project, 'memory/story_state.json',
                             default={'facts': [], 'timeline': [], 'foreshadowing': [], 'open_threads': []})

    def save_story_state(self, project: str, state: dict[str, Any]) -> Path:
        return self.write_json(project, 'memory/story_state.json', state)

    def export_project(self, project: str) -> bytes:
        """Explicit local export, no reference manuscripts or credentials added."""
        output = io.BytesIO()
        root = self.project_dir(project)
        total = 0
        with _LOCK, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob('*')):
                rel = path.relative_to(root)
                if path.is_symlink():
                    raise ValueError('备份不接受符号链接')
                if path.is_file() and rel.parts[0] in {'chapters', 'memory', 'styles'} and not path.name.startswith('.'):
                    total += path.stat().st_size
                    if total > _MAX_ARCHIVE: raise ValueError('项目备份超过100MB')
                    archive.writestr(rel.as_posix(), path.read_bytes())
        if output.tell() > _MAX_ARCHIVE:
            raise ValueError('备份超过 100 MB，请按项目另存')
        return output.getvalue()

    def restore_project(self, archive_bytes: bytes, name: str) -> Path:
        """Validate the complete archive, then create a NEW recovery project."""
        if len(archive_bytes) > _MAX_ARCHIVE:
            raise ValueError('备份文件过大')
        dest = self.root / 'projects' / self.slugify(name)
        if not dest.parent.resolve().is_relative_to(self.root):
            raise ValueError('恢复目录越界')
        if dest.exists():
            raise ValueError('恢复必须使用不存在的新项目名，原项目不会覆盖')
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = archive.infolist()
            if len(members) > 10000 or sum(x.file_size for x in members) > _MAX_ARCHIVE:
                raise ValueError('解压内容超过限制')
            files = []
            seen = set()
            for item in members:
                p = PurePosixPath(item.filename)
                if (p.is_absolute() or '..' in p.parts or '\\' in item.filename or ':' in item.filename
                    or not p.parts or p.parts[0] not in {'chapters', 'memory', 'styles'}
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                    raise ValueError('备份包含不安全路径')
                if item.is_dir():
                    continue
                if item.filename.casefold() in seen or p.suffix not in {'.json', '.jsonl', '.md', '.txt'}:
                    raise ValueError('重复路径或不支持的文件')
                if any(re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', x) or x.endswith((' ', '.')) for x in p.parts):
                    raise ValueError('备份路径在 Windows 上不安全')
                seen.add(item.filename.casefold())
                content = archive.read(item).decode('utf-8')
                if p.suffix == '.json': json.loads(content)
                if p.suffix == '.jsonl':
                    for line in content.splitlines():
                        if line.strip(): json.loads(line)
                files.append((item.filename, content))
            if not files:
                raise ValueError('备份没有可恢复的内容')
        with _LOCK:
            staging = self.root / ('recovery-' + uuid.uuid4().hex)
            staging.mkdir()
            for relative, text in files:
                atomic_write(staging / relative, text)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists(): raise ValueError('恢复项目已存在')
            os.rename(staging, dest)
        return dest
