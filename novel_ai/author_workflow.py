"""Local, explicit author handoffs between outlines, manuscripts and review.

This layer never calls a model, discovers a chapter order, approves prose, or
submits anything to a publishing platform. Saved manuscript bytes remain the
source of truth; plan titles and human scores are used only with matching hashes.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .market_eval import (
    MarketChapter, MarketCorpus, MarketScore, Stage, STAGE_SIZES,
    aggregate_market_scores, market_scoring_csv,
)
from .models import ChapterPlan, SceneBeat
from .outline import HierarchicalOutline, OutlineNode, validate_outline
from .release_pack import ReleasePack
from .storage import ProjectStore


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _outline_path(outline: HierarchicalOutline, node_id: str) -> tuple[HierarchicalOutline, list[OutlineNode]]:
    # Revalidate a copy: Pydantic models may have been mutated after construction.
    checked = validate_outline(HierarchicalOutline.model_validate(outline.model_dump()))

    def find(node: OutlineNode, parents: list[OutlineNode]) -> list[OutlineNode] | None:
        path = [*parents, node]
        if node.id == node_id:
            return path
        for child in node.children:
            found = find(child, path)
            if found is not None:
                return found
        return None

    path = find(checked.root, [])
    if path is None:
        raise ValueError(f"大纲中找不到章节节点: {node_id}")
    if path[-1].level != "chapter":
        raise ValueError("请选择 chapter 层级的节点")
    return checked, path


def _metadata_text(node: OutlineNode, field: str) -> str:
    value = node.metadata.get(field, "")
    if not isinstance(value, str):
        raise ValueError(f"节点 {node.id} 的 {field} 必须是字符串")
    return value


def _metadata_list(node: OutlineNode, field: str) -> list[str]:
    value = node.metadata.get(field, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"节点 {node.id} 的 {field} 必须是字符串列表")
    return list(value)


def chapter_plan_from_outline(outline: HierarchicalOutline, node_id: str) -> ChapterPlan:
    """Convert only the selected chapter; missing causal fields stay editable.

    This is a structural conversion, not approval of a ready-to-draft plan.
    The writer must run its planning-stage gate after the author edits the plan.
    """
    _, path = _outline_path(outline, node_id)
    chapter = path[-1]
    scenes: list[SceneBeat] = []
    seen_numbers: set[int] = set()
    for position, scene in enumerate(chapter.children, start=1):
        number = scene.metadata.get("scene_no", position)
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ValueError(f"节点 {scene.id} 的 scene_no 必须是正整数")
        if number in seen_numbers:
            raise ValueError(f"场景编号重复: {number}")
        seen_numbers.add(number)
        scenes.append(SceneBeat(
            scene_no=number,
            objective=scene.promise,
            opposition=scene.conflict,
            state_change=scene.outcome,
            pov=_metadata_text(scene, "pov"),
            place=_metadata_text(scene, "place"),
            time=_metadata_text(scene, "time"),
            choice=_metadata_text(scene, "choice"),
            cost=_metadata_text(scene, "cost"),
            information_release=_metadata_list(scene, "information_release"),
            foreshadowing=_metadata_list(scene, "foreshadowing"),
            environment_function=_metadata_text(scene, "environment_function"),
            end_hook=_metadata_text(scene, "end_hook"),
        ))
    return ChapterPlan(
        chapter_title=chapter.title,
        chapter_promise=chapter.promise,
        tension_curve=chapter.conflict,
        scenes=scenes,
        must_not_happen=_metadata_list(chapter, "must_not_happen"),
    )


def outline_chapter_context(outline: HierarchicalOutline, node_id: str) -> str:
    """Bounded ancestor, chapter and selected-scene notes, never other chapters."""
    checked, path = _outline_path(outline, node_id)

    def bounded(text: str, maximum: int) -> str:
        marker = "…（上下文截断，请参阅可编辑计划）"
        return text if len(text) <= maximum else text[:maximum - len(marker)] + marker

    def notes_text(node: OutlineNode, field: str) -> str:
        notes = node.metadata.get(field, "")
        if isinstance(notes, str):
            return bounded(notes, 240)
        if isinstance(notes, list) and all(isinstance(note, str) for note in notes):
            return bounded("；".join(notes), 240)
        raise ValueError(f"节点 {node.id} 的 {field} 必须是字符串或字符串列表")

    lines = ["作者确认的层级大纲上下文", f"作品：{bounded(checked.title, 160)}", f"核心设定：{bounded(checked.premise, 600)}"]
    if checked.notes:
        lines.append("全局备注：" + bounded("；".join(checked.notes), 640))
    for node in path:
        lines.append(f"[{node.level}] {bounded(node.title, 160)}")
        for label, value in (("承诺/目标", node.promise), ("冲突", node.conflict), ("结果", node.outcome)):
            if value:
                lines.append(f"{label}：{bounded(value, 360)}")
        for field in ("notes", "author_notes"):
            value = notes_text(node, field)
            if value:
                lines.append(f"作者备注：{value}")
    ancestor_text = bounded("\n".join(lines), 4000)
    scene_lines = ["所选章节的作者场景（不含其他章节）"]
    for position, scene in enumerate(path[-1].children, start=1):
        scene_lines.append(f"[scene {position}] {bounded(scene.title, 120)}")
        for label, value in (("目标/作者正文", scene.promise), ("阻力", scene.conflict), ("状态变化", scene.outcome)):
            if value:
                scene_lines.append(f"{label}：{bounded(value, 240)}")
        for field in ("notes", "author_notes"):
            value = notes_text(scene, field)
            if value:
                scene_lines.append(f"作者备注：{value}")
        for field, label in (
            ("pov", "视角"), ("place", "地点"), ("time", "时间"),
            ("choice", "选择"), ("cost", "代价"),
            ("environment_function", "环境作用"), ("end_hook", "场景钩子"),
        ):
            value = _metadata_text(scene, field)
            if value:
                scene_lines.append(f"{label}：{bounded(value, 160)}")
        for field, label in (("information_release", "信息释放"), ("foreshadowing", "伏笔")):
            values = _metadata_list(scene, field)
            if values:
                scene_lines.append(f"{label}：{bounded('；'.join(values), 240)}")
    if not path[-1].children:
        scene_lines.append("作者尚未提供场景；此处不补造内容。")
    scene_text = bounded("\n".join(scene_lines), 8000 - len(ancestor_text) - 2)
    return ancestor_text + "\n\n" + scene_text


def _chapter_ids(chapter_ids: list[str]) -> list[str]:
    if not isinstance(chapter_ids, list) or not chapter_ids:
        raise ValueError("必须明确提供按阅读顺序排列的章节编号列表")
    # Exact stems, not a sanitizer. Rejecting aliases prevents silent overwrite
    # and mismatches with ProjectStore's historical filename normalization.
    for chapter_id in chapter_ids:
        if not isinstance(chapter_id, str) or not re.fullmatch(r"[\w\-\u4e00-\u9fff]+", chapter_id):
            raise ValueError("章节编号必须是安全的精确文件名，不得包含路径、扩展名或空白")
        if chapter_id.strip("-") != chapter_id:
            raise ValueError("章节编号不得以连字符开头或结尾，避免存储名称变换")
    if len(set(chapter_ids)) != len(chapter_ids):
        raise ValueError("章节编号不得重复")
    return list(chapter_ids)


def _safe_project_path(store: ProjectStore, project: str, *parts: str) -> Path:
    root = Path(store.root).resolve()
    target = root / "projects" / store.slugify(project)
    target = target.joinpath(*parts)
    # Reject links anywhere beneath the configured store root, including links
    # to another book inside that root. Do not create directories while reading.
    current = root
    for part in target.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"项目工作流不读取或写入符号链接: {current.name}")
    if not target.resolve().is_relative_to(root):
        raise ValueError("项目文件路径超出本地存储目录")
    return target


def _read_bytes(path: Path) -> bytes:
    # O_NOFOLLOW also protects the last component if it changes after validation.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        return handle.read()


def _plan_path(store: ProjectStore, project: str, chapter_id: str) -> Path:
    return _safe_project_path(store, project, "memory", "chapter_plans", _digest(chapter_id.encode("utf-8")) + ".json")


def list_author_chapter_ids(store: ProjectStore, project: str) -> list[str]:
    """Inventory safe regular-file stems without opening any manuscript.

    This display order is not a proposed reading order. Linked files and legacy
    names that would require normalization are omitted rather than followed.
    A linked project/chapter directory is rejected as an unsafe storage layout.
    """
    directory = _safe_project_path(store, project, "chapters")
    ids: list[str] = []
    for path in directory.glob("*.md"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            _chapter_ids([path.stem])
        except ValueError:
            continue
        ids.append(path.stem)
    return sorted(ids)


def validate_chapter_target(
    store: ProjectStore, project: str, chapter_id: str, *, allow_overwrite: bool = False,
) -> Path:
    """Preflight a writer destination without creating or opening any files."""
    if not isinstance(project, str) or project != store.slugify(project):
        raise ValueError("请使用规范且唯一的项目名，不得依赖自动名称转换")
    _chapter_ids([chapter_id])
    if len(chapter_id) > 80:
        raise ValueError("新写作章节编号不得超过 80 个字符")
    if not isinstance(allow_overwrite, bool):
        raise ValueError("覆盖已有章节必须由作者明确确认")
    path = _safe_project_path(store, project, "chapters", chapter_id + ".md")
    if path.exists():
        if not path.is_file():
            raise ValueError("章节目标不是普通文件")
        if not allow_overwrite:
            raise ValueError("此编号已有正文，请更换编号，或先备份并明确勾选允许覆盖")
    return path


def chapter_revision_matches(
    store: ProjectStore, project: str, chapter_id: str, text_sha256: str,
) -> bool:
    """Fail closed if saved bytes no longer match a result's recorded revision."""
    if not isinstance(text_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", text_sha256):
        return False
    try:
        path = validate_chapter_target(store, project, chapter_id, allow_overwrite=True)
        return _digest(_read_bytes(path)) == text_sha256.lower()
    except (OSError, UnicodeError, ValueError):
        return False


def _atomic_replace(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".plan-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        return path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_author_chapter(
    store: ProjectStore, project: str, chapter_id: str, text: str, *, allow_overwrite: bool = False,
) -> Path:
    """Save complete manuscript bytes atomically, with no-clobber by default.

    Default publication uses an exclusive hard link, so a chapter created while
    generation is running is never overwritten. Explicit overwrite uses atomic
    replacement; it does not add a multi-process lock or a plan-file transaction.
    """
    path = validate_chapter_target(store, project, chapter_id, allow_overwrite=allow_overwrite)
    if not isinstance(text, str) or not text.strip():
        raise ValueError("章节正文不能为空")
    data = (text.strip() + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".chapter-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        validate_chapter_target(store, project, chapter_id, allow_overwrite=allow_overwrite)
        if allow_overwrite:
            os.replace(temporary, path)
        else:
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise ValueError("章节在保存过程中已被其他操作创建；原文件未覆盖，请重新核对") from exc
        return path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_chapter_plan(store: ProjectStore, project: str, chapter_id: str, plan: ChapterPlan, text: str) -> Path:
    """Atomically bind the approved plan to an already-saved chapter revision.

    ProjectStore writes ``text.strip() + '\\n'``. Verify those actual disk bytes
    before writing provenance; this is not a transaction with manuscript saves.
    """
    manuscript = validate_chapter_target(store, project, chapter_id, allow_overwrite=True)
    checked = ChapterPlan.model_validate(plan.model_dump())
    if not isinstance(text, str) or not text.strip():
        raise ValueError("章节正文不能为空")
    expected = (text.strip() + "\n").encode("utf-8")
    try:
        actual = _read_bytes(manuscript)
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"保存计划前必须先保存章节 {chapter_id}") from exc
    if actual != expected:
        raise ValueError(f"章节 {chapter_id} 的磁盘正文已变化，不能绑定旧计划")
    record = {
        "version": "1", "project": project, "chapter_id": chapter_id,
        "text_sha256": _digest(actual), "plan": checked.model_dump(),
    }
    return _atomic_replace(_plan_path(store, project, chapter_id), _json_bytes(record))


def _saved_title(store: ProjectStore, project: str, chapter_id: str, text_bytes: bytes) -> str:
    path = _plan_path(store, project, chapter_id)
    if not path.exists():
        return chapter_id
    try:
        record = json.loads(_read_bytes(path).decode("utf-8"))
        if not isinstance(record, dict) or any((
            record.get("version") != "1", record.get("project") != project,
            record.get("chapter_id") != chapter_id,
            record.get("text_sha256") != _digest(text_bytes),
        )):
            return chapter_id
        plan = ChapterPlan.model_validate(record.get("plan"))
        return plan.chapter_title.strip() or chapter_id
    except (OSError, UnicodeError, ValueError):
        # A title is optional; the selected manuscript remains authoritative.
        return chapter_id


def load_author_corpus(
    store: ProjectStore, project: str, chapter_ids: list[str], stage: Stage,
    audience: str = "", genre: str = "",
) -> MarketCorpus:
    """Load the author's declared first 3/20 chapters in exactly supplied order."""
    ids = _chapter_ids(chapter_ids)
    if not isinstance(stage, str) or stage not in STAGE_SIZES or len(ids) != STAGE_SIZES[stage]:
        raise ValueError("opening_3 必须明确选择 3 章，retention_20 必须明确选择 20 章")
    chapters: list[MarketChapter] = []
    for number, chapter_id in enumerate(ids, start=1):
        path = _safe_project_path(store, project, "chapters", chapter_id + ".md")
        try:
            data = _read_bytes(path)
            text = data.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"无法读取已保存章节: {chapter_id}") from exc
        chapters.append(MarketChapter(number=number, title=_saved_title(store, project, chapter_id, data), text=text))
    return MarketCorpus(project=project, stage=stage, chapters=chapters, audience=audience, genre=genre).validate_stage()


def release_bundle_bytes(
    corpus: MarketCorpus, pack: ReleasePack, *, chapter_ids: list[str],
    scores: list[MarketScore] | None = None, outline: HierarchicalOutline | None = None,
) -> bytes:
    """Build a deterministic local review candidate, never a release approval."""
    checked = MarketCorpus.model_validate(corpus.model_dump()).validate_stage()
    checked_pack = ReleasePack.model_validate(pack.model_dump())
    ids = _chapter_ids(chapter_ids)
    if len(ids) != len(checked.chapters):
        raise ValueError("章节来源编号与语料章节数不匹配")
    digest = checked.fingerprint()
    if any((
        checked_pack.corpus_sha256 != digest,
        checked_pack.source_stage != checked.stage,
        checked_pack.chapter_count != len(checked.chapters),
    )):
        raise ValueError("发布元数据与当前语料、项目或阶段不匹配")
    for field in ("audience", "genre"):
        if getattr(checked, field) and getattr(checked_pack.profile, field) != getattr(checked, field):
            raise ValueError(f"发布元数据的 {field} 与评审语料不匹配")

    summary: dict[str, Any] | None = None
    checked_scores: list[MarketScore] | None = None
    if scores is not None:
        checked_scores = [MarketScore.model_validate(row.model_dump()) for row in scores]
        summary = aggregate_market_scores(checked_scores)
        if any((
            summary["project"] != checked.project, summary["stage"] != checked.stage,
            summary["corpus_sha256"] != digest,
        )):
            raise ValueError("人工评分与当前语料、项目或阶段不匹配")
    checked_outline = None
    if outline is not None:
        checked_outline = validate_outline(HierarchicalOutline.model_validate(outline.model_dump()))

    status = "human_review_recorded" if summary is not None else "awaiting_human_review"
    chapter_entries = [
        {
            "number": chapter.number, "chapter_id": chapter_id,
            "title": chapter.title, "path": f"chapters/{chapter.number:03d}.md",
            "text_sha256": _digest(chapter.text.encode("utf-8")),
        }
        for chapter_id, chapter in zip(ids, checked.chapters)
    ]
    manifest = {
        "version": "1", "kind": "local_review_candidate", "project": checked.project,
        "stage": checked.stage, "corpus_sha256": digest,
        "corpus_fingerprint_schema": "market-corpus-v2",
        "audience": checked.audience, "genre": checked.genre, "review_note": checked.review_note,
        "chapter_order": "author_declared", "chapters": chapter_entries,
        "human_review_status": status, "publishability_verdict": None,
        "outline_status": "author_supplied_context_not_chapter_provenance" if checked_outline else "not_included",
    }
    entries: list[tuple[str, bytes]] = [
        ("manifest.json", _json_bytes(manifest)),
        ("release_pack.json", _json_bytes(checked_pack.model_dump())),
        ("market_scoring.csv", market_scoring_csv(checked).encode("utf-8-sig")),
    ]
    entries.extend((entry["path"], chapter.text.encode("utf-8")) for entry, chapter in zip(chapter_entries, checked.chapters))
    if checked_scores is not None:
        # Canonical ordering also makes equivalent reviewer submissions stable.
        entries.append(("human_scores.json", _json_bytes([row.model_dump() for row in sorted(checked_scores, key=lambda row: row.dimension)])))
        entries.append(("human_review_summary.json", _json_bytes(summary)))
    if checked_outline is not None:
        entries.append(("outline.json", _json_bytes(checked_outline.model_dump())))
    readme = (
        "Novel 本地发布前审阅候选包 / Local review candidate\n\n"
        f"人工评分状态 / Human review status: {status}\n"
        "本包不是发布许可或质量认证，也不保证平台推荐、签约、收益或可发布性。\n"
        "This is not certified publishable and has not been submitted to any platform.\n"
        "章节范围及顺序由作者明确指定；工具无法证明其为作品实际的前 3/20 章。\n"
        "manifest.json 记录原章节编号、精确正文摘要、题材、读者与语料指纹。\n"
        "market_scoring.csv 是空白人工评分表；须由同一评审者完整填写十个维度。\n"
        "人工评分仅对应本包的精确语料及评审背景。修改后须重新生成并人工评分。\n"
        "outline.json 如存在，仅是作者提供的上下文，未证明与各章最终正文一致。\n"
    )
    entries.append(("README.txt", readme.encode("utf-8")))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100600 << 16
            archive.writestr(info, data)
    return output.getvalue()


def save_release_bundle(store: ProjectStore, project: str, bundle: bytes) -> Path:
    """Publish complete bytes once; identical retries reuse the verified artifact.

    A same-directory hard link provides atomic exclusive publication. Failure
    leaves no partial target and never replaces an existing release candidate.
    """
    if not isinstance(bundle, bytes) or not bundle:
        raise ValueError("发布包必须是非空 bytes")
    try:
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("project") != project or manifest.get("kind") != "local_review_candidate":
                raise ValueError("发布包与当前项目不匹配")
    except (zipfile.BadZipFile, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("发布包缺少有效的项目清单") from exc
    path = _safe_project_path(store, project, "exports", f"release-{_digest(bundle)}.zip")

    def reuse_existing() -> Path:
        existing = _safe_project_path(store, project, "exports", path.name)
        if _read_bytes(existing) != bundle:
            raise ValueError("同名发布包内容不匹配；保留原文件，请检查存储完整性")
        return existing

    if path.exists():
        return reuse_existing()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".release-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(bundle)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return reuse_existing()
        return path
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
