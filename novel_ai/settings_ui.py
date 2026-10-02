"""Freeze settings saves and advance the session only from complete readback."""
import hashlib
import json
from copy import deepcopy
from uuid import uuid4

from .author_workflow import save_workbench_story_settings, story_bible_digest
from .settings_commit import SETTINGS_PATHS, SettingsCommitError, load_settings_bundle


def settings_input_binding(files):
    return hashlib.sha256(json.dumps(files, ensure_ascii=False, sort_keys=True,
                                   allow_nan=False).encode("utf-8")).hexdigest()


def require_current_settings(state, store, project):
    if state.get("settings_pending") is not None:
        raise SettingsCommitError("本次设定保存仍待核对，请先重试原操作或在新会话读取核对")
    expected = state.get("settings_snapshot")
    if not isinstance(expected, dict):
        raise SettingsCommitError("故事设定与平面总纲来源不可用，请在新会话实际读取当前项目")
    actual = load_settings_bundle(store, project)
    if actual["sha256"] != expected.get("sha256"):
        raise SettingsCommitError("故事设定或平面总纲已变化；当前编辑已保留，请下载草案后重新读取并核对")
    return deepcopy(expected)


def freeze_settings_request(state, store, project, *, files, expected_before, binding):
    if state.get("settings_pending") is not None:
        raise SettingsCommitError("已有设定保存待核对，不能用新输入替换原操作")
    if binding != settings_input_binding(files) or expected_before != state.get("settings_snapshot", {}).get("sha256"):
        raise SettingsCommitError("保存输入与实际加载的设定来源不一致")
    state["settings_pending"] = deepcopy({"project": store.slugify(project), "root": str(store.root),
        "request_id": uuid4().hex, "files": files, "expected_before": expected_before, "binding": binding})


def commit_pending_settings(state, store, project, *, binding):
    pending = deepcopy(state.get("settings_pending"))
    if (not isinstance(pending, dict) or pending.get("project") != store.slugify(project)
            or pending.get("root") != str(store.root) or pending.get("binding") != binding):
        raise SettingsCommitError("待保存设定与当前项目或输入不一致，请保留新编辑并核对原操作")
    if (pending["binding"] != settings_input_binding(pending["files"])
            or pending["expected_before"] != state.get("settings_snapshot", {}).get("sha256")):
        raise SettingsCommitError("原保存请求或加载基线已变化，请保留证据后核对")
    result = save_workbench_story_settings(store, project, files=pending["files"],
        expected_before=pending["expected_before"], request_id=pending["request_id"])
    if result["historical"]:
        raise SettingsCommitError("原设定保存已有回执，但当前文件已经更新；未覆盖新版本，请下载草案并在新会话读取核对")
    snapshot = result["current"]
    state["settings_snapshot"] = deepcopy(snapshot)
    state["memory_source_bible"] = deepcopy(snapshot["bible"])
    state["story_bible_source_sha256"] = (story_bible_digest(snapshot["bible"])
        if snapshot["sha256"][SETTINGS_PATHS[0]] is not None else None)
    state["settings_pending"] = None
    return result
