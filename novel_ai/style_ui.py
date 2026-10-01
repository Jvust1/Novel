"""Freeze Style Lab save requests and publish session state only after readback."""
import hashlib
import json
from copy import deepcopy
from uuid import uuid4

from .style_commit import StyleCommitError, commit_style_bundle, load_style_bundle


def style_input_binding(*, project, source, name, weight, encoding, semantic, notes):
    data = {"project": project, "source": source, "name": name, "weight": weight,
            "encoding": encoding, "semantic": semantic, "notes": notes}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                   allow_nan=False).encode("utf-8")).hexdigest()


def apply_style_snapshot(state, snapshot):
    state["style_profiles"] = deepcopy(snapshot["profiles"])
    state["style"] = deepcopy(snapshot["style"])
    state["reference_hashes"] = set(snapshot["signature"]["hashes"])
    state["style_snapshot"] = deepcopy(snapshot)


def require_current_style(state, store, project):
    actual = load_style_bundle(store, project)
    expected = state.get("style_snapshot")
    if not isinstance(expected, dict) or actual["sha256"] != expected.get("sha256"):
        raise StyleCommitError("风格资料已更新，请先重新读取；本次尚未分析或请求模型")
    return deepcopy(expected)


def freeze_style_request(state, store, project, *, files, expected_before, binding, kind):
    if state.get("style_pending") is not None:
        raise StyleCommitError("已有风格保存待核对，请先重试或重新读取")
    if kind not in {"add", "clear"}:
        raise StyleCommitError("未知风格保存动作")
    state["style_pending"] = deepcopy({"project": store.slugify(project), "root": str(store.root),
                                      "request_id": uuid4().hex,
                                      "files": files, "expected_before": expected_before,
                                      "binding": binding, "kind": kind})


def commit_pending_style(state, store, project, *, binding):
    pending = deepcopy(state.get("style_pending"))
    if (not isinstance(pending, dict) or pending.get("project") != store.slugify(project)
            or pending.get("root") != str(store.root) or pending.get("binding") != binding):
        raise StyleCommitError("待保存风格与当前项目或输入不一致，请恢复原选择或重新读取已保存资料")
    result = commit_style_bundle(store, project, files=pending["files"], expected_before=pending["expected_before"],
                                 request_id=pending["request_id"])
    apply_style_snapshot(state, result["current"])
    state["style_pending"] = None
    return result


def refresh_saved_styles(state, store, project):
    snapshot = load_style_bundle(store, project)
    apply_style_snapshot(state, snapshot)
    state["style_pending"] = None
    return snapshot
