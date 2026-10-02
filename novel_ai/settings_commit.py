"""Recoverable publication of the two existing local story-setting files.

Adapt the fixed-image Style Lab protocol, retaining ProjectStore's licensed
atomic writer and stable native project lock. No generic transaction service,
author acceptance, remote storage or hostile-directory guarantee is added.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy

from ._vendor.boltons_atomic import sync_directory
from .models import StoryBible
from .storage_guard import project_lock, reject_links

SETTINGS_PATHS = ("memory/story_bible.json", "memory/outline.json")
INTENT_PATH = ".settings-commit-transaction.json"
SCHEMA = "story-settings-commit-v1"
MAX_BYTES = 64 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_OTHER_INTENTS = (".style-commit-transaction.json", ".memory-commit-transaction.json", ".extraction-transaction.json")


class SettingsCommitError(ValueError):
    """Preserve the saved settings and operation evidence before reconciling."""


def _json(value):
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise SettingsCommitError("故事设定超过保存大小限制")
        return text
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise SettingsCommitError("故事设定含无效 JSON 或超过大小限制") from exc


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise SettingsCommitError("故事设定包含重复 JSON 字段")
        result[key] = value
    return result


def _loads(raw):
    try:
        if not isinstance(raw, (bytes, str)) or len(raw.encode("utf-8") if isinstance(raw, str) else raw) > MAX_BYTES:
            raise SettingsCommitError("故事设定无效或过大")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        value = json.loads(raw, object_pairs_hook=_pairs)
        _json(value)
        return value
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise SettingsCommitError("故事设定或恢复记录损坏，请保留原件并核对") from exc


def _sha(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _read(path):
    reject_links(path)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise SettingsCommitError("故事设定不是受支持的有界普通文件")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise SettingsCommitError("故事设定超过保存大小限制")
    return raw


def _project(store, project):
    if not isinstance(project, str):
        raise SettingsCommitError("项目必须是明确文本")
    return store.slugify(project)


def _hashes(value):
    if not isinstance(value, dict) or set(value) != set(SETTINGS_PATHS):
        raise SettingsCommitError("设定版本必须包含故事设定与平面总纲两个来源")
    if any(v is not None and (not isinstance(v, str) or not _SHA.fullmatch(v)) for v in value.values()):
        raise SettingsCommitError("设定版本必须使用原文件 SHA256")


def _validate(bible, outline):
    _json([bible, outline])
    if not isinstance(bible, dict) or not isinstance(outline, dict):
        raise SettingsCommitError("故事设定与总纲必须分别是 JSON 对象")
    try:
        StoryBible.model_validate(bible, strict=True)
    except ValueError as exc:
        raise SettingsCommitError("故事设定字段无效，请保留原件并核对") from exc
    if not isinstance(outline.get("outline", ""), str):
        raise SettingsCommitError("平面总纲正文必须是文本")


def _aliases(paths):
    present = [path for path in paths if path.exists()]
    for path in present:
        reject_links(path)
    identities = [(path.stat().st_dev, path.stat().st_ino) for path in present]
    if len(set(identities)) != len(identities):
        raise SettingsCommitError("设定文件与恢复证据不能互为硬链接别名")


def _raw(store, project):
    paths = [store._path(project, p) for p in SETTINGS_PATHS]
    _aliases(paths)
    return {p: _read(path) for p, path in zip(SETTINGS_PATHS, paths)}


def _bundle(raw):
    # Legacy projects may have either file independently missing.
    bible, outline = ({} if raw[p] is None else _loads(raw[p]) for p in SETTINGS_PATHS)
    _validate(bible, outline)
    return {"bible": deepcopy(bible), "outline": deepcopy(outline),
            "sha256": {p: _sha(raw[p]) for p in SETTINGS_PATHS}}


def load_settings_bundle(store, project):
    project = _project(store, project)
    with store._guard(project):
        return _bundle(_raw(store, project))


def prepare_settings_save(snapshot, bible, outline):
    snapshot, bible = deepcopy((snapshot, bible))
    _hashes(snapshot["sha256"])
    _validate(snapshot["bible"], snapshot["outline"])
    if not isinstance(bible, dict) or not isinstance(outline, str):
        raise SettingsCommitError("故事设定保存需要明确对象和总纲文本")
    desired_bible = {**snapshot["bible"], **bible}
    desired_outline = {**snapshot["outline"], "outline": outline}
    _validate(desired_bible, desired_outline)
    return {p: _json(value) + "\n" for p, value in zip(SETTINGS_PATHS, (desired_bible, desired_outline))}


def _request(store, project, files, before, request_id):
    if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
        raise SettingsCommitError("设定保存需要本次操作固定的请求标识")
    _hashes(before)
    if not isinstance(files, dict) or set(files) != set(SETTINGS_PATHS) or any(not isinstance(s, str) for s in files.values()):
        raise SettingsCommitError("设定保存必须包含两个固定 UTF8 文件")
    _validate(*[_loads(files[p]) for p in SETTINGS_PATHS])
    receipt = {"schema": SCHEMA, "request_id": request_id, "project": project,
               "root": str(store.project_dir(project).resolve()), "before": deepcopy(before),
               "after": {p: _sha(files[p].encode("utf-8")) for p in SETTINGS_PATHS}}
    identity = {k: receipt[k] for k in ("schema", "request_id", "project", "root")}
    receipt["operation_id"] = "settings-" + _sha(_json(identity).encode("utf-8"))
    return receipt


def _receipt_path(store, project, receipt):
    return store._path(project, "memory/settings_commits/" + receipt["operation_id"] + ".json")


def _check_aliases(store, project, receipt):
    _aliases([*(store._path(project, p) for p in SETTINGS_PATHS),
              store._path(project, INTENT_PATH, internal=True), _receipt_path(store, project, receipt)])


def _existing_receipt(store, project, receipt):
    raw = _read(_receipt_path(store, project, receipt))
    if raw is None:
        return False
    if _loads(raw) != receipt:
        raise SettingsCommitError("已有设定保存回执冲突，请保留证据后核对")
    return True


def _parse_intent(store, project, raw):
    value = _loads(raw)
    if not isinstance(value, dict) or set(value) != {"schema", "receipt", "before", "files"} or value["schema"] != SCHEMA:
        raise SettingsCommitError("设定恢复记录无效")
    old = value["before"]
    if not isinstance(old, dict) or set(old) != set(SETTINGS_PATHS) or any(v is not None and not isinstance(v, str) for v in old.values()):
        raise SettingsCommitError("设定恢复记录缺少完整旧内容")
    old_raw = {p: text.encode("utf-8") if text is not None else None for p, text in old.items()}
    _bundle(old_raw)
    if not isinstance(value["receipt"], dict):
        raise SettingsCommitError("设定恢复回执无效")
    receipt = _request(store, project, value["files"], {p: _sha(old_raw[p]) for p in SETTINGS_PATHS}, value["receipt"].get("request_id"))
    if value["receipt"] != receipt:
        raise SettingsCommitError("设定恢复记录身份或摘要不匹配")
    return value


def _no_other_intent(store, project):
    for name in _OTHER_INTENTS:
        if _read(store._path(project, name, internal=True)) is not None:
            raise SettingsCommitError("另一个项目保存尚未恢复，先核对其状态")


def _sync(store, project):
    root = store.project_dir(project)
    for path in (root / "memory/settings_commits", root / "memory", root):
        if path.exists():
            reject_links(path)
            sync_directory(path)


def _check_images(store, project, receipt, *, after_only=False):
    _check_aliases(store, project, receipt)
    raw = _raw(store, project)
    for p in SETTINGS_PATHS:
        allowed = {receipt["after"][p]} if after_only else {receipt["before"][p], receipt["after"][p]}
        if _sha(raw[p]) not in allowed:
            raise SettingsCommitError("设定文件已独立改变，保留待恢复记录并核对")


def _recover_locked(store, project):
    path = store._path(project, INTENT_PATH, internal=True)
    raw = _read(path)
    if raw is None:
        return None
    _no_other_intent(store, project)
    intent = _parse_intent(store, project, raw)
    receipt = intent["receipt"]
    _check_aliases(store, project, receipt)
    if not _existing_receipt(store, project, receipt):
        _check_images(store, project, receipt)
        for p in SETTINGS_PATHS:
            _check_images(store, project, receipt)
            target = store._path(project, p)
            if _sha(_read(target)) != receipt["after"][p]:
                store._write(target, intent["files"][p])
            if _sha(_read(target)) != receipt["after"][p]:
                raise SettingsCommitError("设定文件读回不一致，保存仍待恢复")
        _check_images(store, project, receipt, after_only=True)
        _sync(store, project)
        store._write(_receipt_path(store, project, receipt), _json(receipt) + "\n", overwrite=False)
        if not _existing_receipt(store, project, receipt):
            raise SettingsCommitError("设定保存回执读回失败")
    # A valid receipt records history, never permission to replay over newer data.
    _sync(store, project)
    path.unlink()
    sync_directory(path.parent)
    return receipt


def recover_settings_commit(store, project):
    project = _project(store, project)
    with project_lock(store._path(project, ".store.lock", internal=True)):
        return _recover_locked(store, project)


def commit_settings_bundle(store, project, *, files, expected_before, request_id):
    """Publish or recover this exact request; an exception is not a rollback."""
    project = _project(store, project)
    files, expected_before = deepcopy((files, expected_before))
    with project_lock(store._path(project, ".store.lock", internal=True)):
        _no_other_intent(store, project)
        receipt = _request(store, project, files, expected_before, request_id)
        _check_aliases(store, project, receipt)
        intent_path = store._path(project, INTENT_PATH, internal=True)
        existing = _read(intent_path)
        if existing is not None:
            pending = _parse_intent(store, project, existing)
            if pending["receipt"] != receipt:
                raise SettingsCommitError("另一项设定保存仍待恢复，不能覆盖其记录")
            _recover_locked(store, project)
        elif not _existing_receipt(store, project, receipt):
            before = _raw(store, project)
            _bundle(before)
            if {p: _sha(before[p]) for p in SETTINGS_PATHS} != expected_before:
                raise SettingsCommitError("故事设定或平面总纲已被另一个会话更新，请保留编辑并重新读取核对")
            intent = {"schema": SCHEMA, "receipt": receipt,
                      "before": {p: before[p].decode("utf-8") if before[p] is not None else None for p in SETTINGS_PATHS},
                      "files": files}
            serialized = _json(intent) + "\n"
            if len(serialized.encode("utf-8")) > MAX_BYTES:
                raise SettingsCommitError("完整设定保存记录超过大小限制，尚未写入")
            _parse_intent(store, project, serialized.encode("utf-8"))
            if {p: _sha(raw) for p, raw in _raw(store, project).items()} != expected_before:
                raise SettingsCommitError("设定来源在保存前改变，尚未写入")
            store._write(intent_path, serialized, overwrite=False)
            if _read(intent_path) != serialized.encode("utf-8"):
                raise SettingsCommitError("设定保存意图读回失败，未报告保存成功")
            sync_directory(intent_path.parent)
            _recover_locked(store, project)
        if not _existing_receipt(store, project, receipt):
            raise SettingsCommitError("设定保存没有实际回执，不能报告成功")
        current = _bundle(_raw(store, project))
        return {"receipt": deepcopy(receipt), "current": current,
                "historical": current["sha256"] != receipt["after"]}
