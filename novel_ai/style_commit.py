"""Bounded, recoverable Style Lab publication using the existing local store.

Three fixed after-images, one immutable receipt and optimistic source checks.
The licensed boltons writer and native project lock remain the actual storage
primitives. This is a cooperating local protocol, not a remote transaction.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy

from ._vendor.boltons_atomic import sync_directory
from .models import StyleFingerprint
from .storage_guard import project_lock, reject_links
from .style_engine import blend_styles

STYLE_PATHS = ("styles/style_profiles.json", "styles/style_dna.json", "styles/reference_signature.json")
INTENT_PATH = ".style-commit-transaction.json"
SCHEMA = "style-commit-v1"
MAX_BYTES = 64 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SHINGLE = re.compile(r"[0-9a-f]{20}\Z")


class StyleCommitError(ValueError):
    """Preserve existing style evidence and reconcile before proceeding."""


def _json(value):
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise StyleCommitError("风格资料超过保存大小限制")
        return text
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise StyleCommitError("风格资料含无效 JSON 或超过大小限制") from exc


def _pairs(rows):
    out = {}
    for key, value in rows:
        if key in out:
            raise StyleCommitError("风格资料包含重复 JSON 字段")
        out[key] = value
    return out


def _loads(raw):
    try:
        if not isinstance(raw, (bytes, str)) or len(raw.encode("utf-8") if isinstance(raw, str) else raw) > MAX_BYTES:
            raise StyleCommitError("风格资料无效或过大")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        value = json.loads(raw, object_pairs_hook=_pairs)
        _json(value)
        return value
    except (TypeError, ValueError, UnicodeError, OverflowError, RecursionError) as exc:
        raise StyleCommitError("风格资料损坏，保留原件后核对") from exc


def _sha(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _read(path):
    reject_links(path)
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise StyleCommitError("风格资料不是受支持的有界普通文件")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise StyleCommitError("风格资料超过保存大小限制")
    return raw


def _project(store, project):
    if not isinstance(project, str):
        raise StyleCommitError("项目必须是明确文本")
    return store.slugify(project)


def _hashes(value):
    if not isinstance(value, dict) or set(value) != set(STYLE_PATHS):
        raise StyleCommitError("风格版本必须包含完整三个来源")
    if any(v is not None and (not isinstance(v, str) or not _SHA.fullmatch(v)) for v in value.values()):
        raise StyleCommitError("风格版本必须使用原文件 SHA256")


def _validate(profiles, style, signature, *, generated=False):
    _json([profiles, style, signature])
    if not isinstance(profiles, list):
        raise StyleCommitError("风格来源必须是列表")
    weighted = []
    for row in profiles:
        if (not isinstance(row, dict) or not isinstance(row.get("name"), str)
                or not isinstance(row.get("fingerprint"), dict)):
            raise StyleCommitError("风格来源缺少名称或特征")
        weight = row.get("weight")
        try:
            valid_weight = type(weight) in (int, float) and math.isfinite(weight) and weight > 0
        except OverflowError:
            valid_weight = False
        if not valid_weight:
            raise StyleCommitError("风格权重必须是有限正数")
        try:
            fp = StyleFingerprint.model_validate(row["fingerprint"])
            _json(fp.model_dump())
        except ValueError as exc:
            raise StyleCommitError("风格特征无效") from exc
        weighted.append((fp, weight))
    if (not isinstance(signature, dict) or type(signature.get("shingle_chars")) is not int
            or signature["shingle_chars"] != 18 or not isinstance(signature.get("hashes"), list)
            or any(not isinstance(h, str) or not _SHINGLE.fullmatch(h) for h in signature["hashes"])
            or len(set(signature["hashes"])) != len(signature["hashes"])):
        raise StyleCommitError("参考签名必须是无重复的十八字片段摘要")
    if not profiles:
        if style is not None or signature["hashes"]:
            raise StyleCommitError("空风格库不能保留综合风格或旧签名")
    elif not isinstance(style, dict):
        raise StyleCommitError("风格来源缺少综合风格")
    else:
        try:
            normalized = StyleFingerprint.model_validate(style).model_dump()
            _json(normalized)
        except ValueError as exc:
            raise StyleCommitError("综合风格无效") from exc
        if generated and normalized != blend_styles(weighted, name="Novel-Composite").model_dump():
            raise StyleCommitError("综合风格含手动覆盖或与来源不一致，请先核对；原资料未改动")


def _bundle(raw):
    if all(v is None for v in raw.values()):
        profiles, style, signature = [], None, {"hashes": [], "shingle_chars": 18}
    elif any(v is None for v in raw.values()):
        raise StyleCommitError("旧风格资料缺少配套文件，请保留原件并核对，不能猜补综合风格或签名")
    else:
        profiles, style, signature = (_loads(raw[p]) for p in STYLE_PATHS)
    _validate(profiles, style, signature)
    return {"profiles": deepcopy(profiles), "style": deepcopy(style), "signature": deepcopy(signature),
            "sha256": {p: _sha(raw[p]) for p in STYLE_PATHS}}


def _raw(store, project):
    paths = [store._path(project, p) for p in STYLE_PATHS]
    raw = {p: _read(path) for p, path in zip(STYLE_PATHS, paths)}
    present = [path for path in paths if path.exists()]
    identities = [(p.stat().st_dev, p.stat().st_ino) for p in present]
    if len(set(identities)) != len(identities):
        raise StyleCommitError("风格文件不能互为硬链接别名")
    return raw


def load_style_bundle(store, project):
    project = _project(store, project)
    with store._guard(project):
        return _bundle(_raw(store, project))


def _files(profiles, style, signature):
    _validate(profiles, style, signature, generated=True)
    return {p: _json(v) + "\n" for p, v in zip(STYLE_PATHS, (profiles, style, signature))}


def prepare_style_addition(snapshot, profile, signature):
    snapshot, profile, signature = deepcopy((snapshot, profile, signature))
    _hashes(snapshot["sha256"])
    _validate(snapshot["profiles"], snapshot["style"], snapshot["signature"], generated=True)
    if not isinstance(signature, set):
        raise StyleCommitError("新增签名必须是明确集合")
    if not isinstance(profile, dict) or not isinstance(profile.get("name"), str) or not profile["name"].strip():
        raise StyleCommitError("新增风格来源需要明确名称")
    profiles = snapshot["profiles"] + [profile]
    # Validate the source before using any values in the blending implementation.
    _validate([profile], profile.get("fingerprint") if isinstance(profile, dict) else None,
              {"hashes": list(signature), "shingle_chars": 18})
    style = dict(snapshot["style"] or {})
    style.update(blend_styles([(StyleFingerprint.model_validate(row["fingerprint"]), row["weight"])
                              for row in profiles], name="Novel-Composite").model_dump())
    hashes = sorted(set(snapshot["signature"]["hashes"]) | signature)
    sig = {**snapshot["signature"], "hashes": hashes, "shingle_chars": 18}
    return _files(profiles, style, sig)


def prepare_style_clear(snapshot):
    _hashes(snapshot["sha256"])
    _validate(snapshot["profiles"], snapshot["style"], snapshot["signature"])
    return _files([], None, {"hashes": [], "shingle_chars": 18})


def _request(store, project, files, before, request_id):
    if not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id):
        raise StyleCommitError("风格保存需要本次操作固定的请求标识")
    _hashes(before)
    if not isinstance(files, dict) or set(files) != set(STYLE_PATHS) or any(not isinstance(s, str) for s in files.values()):
        raise StyleCommitError("风格保存必须包含三个固定 UTF8 文件")
    values = [_loads(files[p]) for p in STYLE_PATHS]
    _validate(*values, generated=True)
    receipt = {"schema": SCHEMA, "request_id": request_id, "project": project, "root": str(store.project_dir(project).resolve()),
               "before": deepcopy(before), "after": {p: _sha(files[p].encode("utf-8")) for p in STYLE_PATHS}}
    identity = {k: receipt[k] for k in ("schema", "request_id", "project", "root")}
    receipt["operation_id"] = "style-" + _sha(_json(identity).encode("utf-8"))
    return receipt


def _receipt_path(store, project, receipt):
    return store._path(project, "styles/commits/" + receipt["operation_id"] + ".json")


def _existing_receipt(store, project, receipt):
    raw = _read(_receipt_path(store, project, receipt))
    if raw is None:
        return False
    if _loads(raw) != receipt:
        raise StyleCommitError("已有风格保存回执冲突，请保留证据后核对")
    return True


def _parse_intent(store, project, raw):
    value = _loads(raw)
    if not isinstance(value, dict) or set(value) != {"schema", "receipt", "before", "files"} or value["schema"] != SCHEMA:
        raise StyleCommitError("风格恢复记录无效")
    old = value["before"]
    if not isinstance(old, dict) or set(old) != set(STYLE_PATHS) or any(v is not None and not isinstance(v, str) for v in old.values()):
        raise StyleCommitError("风格恢复记录缺少完整旧内容")
    old_raw = {p: text.encode("utf-8") if text is not None else None for p, text in old.items()}
    _bundle(old_raw)
    if not isinstance(value["receipt"], dict):
        raise StyleCommitError("风格恢复回执无效")
    receipt = _request(store, project, value["files"], {p: _sha(old_raw[p]) for p in STYLE_PATHS}, value["receipt"].get("request_id"))
    if value["receipt"] != receipt:
        raise StyleCommitError("风格恢复记录身份或摘要不匹配")
    return value


def _no_other_intent(store, project):
    for name in (".memory-commit-transaction.json", ".extraction-transaction.json"):
        if _read(store._path(project, name, internal=True)) is not None:
            raise StyleCommitError("另一个项目保存尚未恢复，先核对其状态")


def _sync(store, project):
    root = store.project_dir(project)
    for path in (root / "styles/commits", root / "styles", root):
        if path.exists():
            reject_links(path)
            sync_directory(path)


def _check_images(store, project, receipt, *, after_only=False):
    raw = _raw(store, project)
    for p in STYLE_PATHS:
        allowed = {receipt["after"][p]} if after_only else {receipt["before"][p], receipt["after"][p]}
        if _sha(raw[p]) not in allowed:
            raise StyleCommitError("风格文件已独立改变，保留待恢复记录并核对")


def _recover_locked(store, project):
    path = store._path(project, INTENT_PATH, internal=True)
    raw = _read(path)
    if raw is None:
        return None
    _no_other_intent(store, project)
    intent = _parse_intent(store, project, raw)
    receipt = intent["receipt"]
    if not _existing_receipt(store, project, receipt):
        _check_images(store, project, receipt)
        for p in STYLE_PATHS:
            _check_images(store, project, receipt)
            target = store._path(project, p)
            if _sha(_read(target)) != receipt["after"][p]:
                store._write(target, intent["files"][p])
            if _sha(_read(target)) != receipt["after"][p]:
                raise StyleCommitError("风格文件读回不一致，保存仍待恢复")
        _check_images(store, project, receipt, after_only=True)
        _sync(store, project)
        store._write(_receipt_path(store, project, receipt), _json(receipt) + "\n", overwrite=False)
        if not _existing_receipt(store, project, receipt):
            raise StyleCommitError("风格保存回执读回失败")
    # A published receipt is historical success. Never replay it over newer data.
    _sync(store, project)
    path.unlink()
    sync_directory(path.parent)
    return receipt


def recover_style_commit(store, project):
    project = _project(store, project)
    with project_lock(store._path(project, ".store.lock", internal=True)):
        return _recover_locked(store, project)


def commit_style_bundle(store, project, *, files, expected_before, request_id):
    """Publish once, recover exact retries, then return the actual current set.

    An exception can follow publication. Retain this exact request and retry;
    neither an exception nor a historical receipt is a rollback/currentness claim.
    """
    project = _project(store, project)
    files, expected_before = deepcopy((files, expected_before))
    with project_lock(store._path(project, ".store.lock", internal=True)):
        _no_other_intent(store, project)
        receipt = _request(store, project, files, expected_before, request_id)
        intent_path = store._path(project, INTENT_PATH, internal=True)
        existing = _read(intent_path)
        if existing is not None:
            pending = _parse_intent(store, project, existing)
            if pending["receipt"] != receipt:
                raise StyleCommitError("另一项风格保存仍待恢复，不能覆盖其记录")
            _recover_locked(store, project)
        elif not _existing_receipt(store, project, receipt):
            before = _raw(store, project)
            _bundle(before)
            if {p: _sha(before[p]) for p in STYLE_PATHS} != expected_before:
                raise StyleCommitError("风格资料已被另一个会话更新，请重新读取后再分析")
            intent = {"schema": SCHEMA, "receipt": receipt,
                      "before": {p: before[p].decode("utf-8") if before[p] is not None else None for p in STYLE_PATHS},
                      "files": files}
            serialized = _json(intent) + "\n"
            if len(serialized.encode("utf-8")) > MAX_BYTES:
                raise StyleCommitError("完整风格保存记录超过大小限制，尚未写入")
            store._write(intent_path, serialized, overwrite=False)
            if _read(intent_path) != serialized.encode("utf-8"):
                raise StyleCommitError("风格保存意图读回失败，未报告保存成功")
            sync_directory(intent_path.parent)
            _recover_locked(store, project)
        if not _existing_receipt(store, project, receipt):
            raise StyleCommitError("风格保存没有实际回执，不能报告成功")
        current = _bundle(_raw(store, project))
        return {"receipt": deepcopy(receipt), "current": current, "historical": current["sha256"] != receipt["after"]}
