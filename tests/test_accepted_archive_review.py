"""Independent synthetic probes for accepted archive continuation boundaries."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import itertools
import json
from pathlib import Path

import httpx
import pytest

from novel_ai import accepted_writing as writing
from novel_ai import gpt_story_state as protocol
from novel_ai.budgeted_writing import BudgetedWritingSession
from novel_ai.orchestration import RouterConfig
from novel_ai.provider import ProviderConfig, OpenAICompatibleProvider
from novel_ai.request_budget import RequestBudget, RequestBudgetLimits

COUNTER = itertools.count()
PLAN = {"chapter_title": "归铃", "scenes": [{"scene_no": 1, "pov": "薛遥", "objective": "归还铜铃", "opposition": "船夫已走", "choice": "留下等待", "cost": "错过渡船", "state_change": "决定留宿"}]}
OLD = "薛遥说：“铃还在这里。”\n薛遥问：“你明天回来吗？”"
NEW = "薛遥把铜铃放在桌上，推开了侧门。"


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def artifact(text, name): return protocol.artifact(text, source_id=name, location="private://synthetic/" + name, revision=1).model_dump(mode="json")
def step(state, action, payload):
    return protocol.transition(state, {"action": action, "story_id": state.story_id,
        "base_story_revision": state.revision, "expected_state_sha256": protocol.state_fingerprint(state),
        "operation_id": "independent-" + str(next(COUNTER)), "payload": payload})
def confirmation(state, scope):
    p = state.progress
    record = {"confirmed_by": "author", "confirmation_source": "synthetic-only://explicit-test-action",
        "story_id": state.story_id, "story_revision": p.base_story_revision, "chapter_id": p.chapter_id,
        "plan_revision": p.plan_revision, "plan_source_fingerprint": protocol.source_fingerprint(p.plan)}
    if scope != "plan": record.update(draft_revision=p.draft_revision, draft_source_fingerprint=protocol.source_fingerprint(p.draft))
    if scope == "memory": record["memory_update_id"] = p.memory_update_id
    return record


def make_archive(tmp_path, *, revision=1, characters=None, historical_plan=None, canon_extra=None, style=None):
    s = protocol.create_state("river", template={"canon": {**(canon_extra or {}), "characters": characters if characters is not None else [{"name": "薛遥", "knows": [], "custom_voice": {"cadence": ["短句"]}}]}, "style_profile": style or {"custom_style": {"pace": "slow"}}})
    path = tmp_path / "synthetic.json"
    if revision:
        s = step(s, "start_chapter", {"chapter_id": "c01"})
        s = step(s, "set_plan", {"artifact": artifact(historical_plan or json.dumps(PLAN, ensure_ascii=False), "old-plan")})
        s = step(s, "accept_plan", {"confirmation": confirmation(s, "plan")})
        s = step(s, "set_draft", {"artifact": artifact(OLD, "old-prose")})
        s = step(s, "review", {"draft_revision": 1, "issues": [], "source": artifact("合成审校", "review")["source"]})
        s = step(s, "accept_chapter", {"confirmation": confirmation(s, "chapter")})
        s = step(s, "propose_memory", {"changes": []})
        s = step(s, "accept_memory", {"confirmation": confirmation(s, "memory")})
        s = step(s, "apply_memory", {"memory_update_id": s.progress.memory_update_id})
        saved = protocol.save_state(path, s)
        s = protocol.load_state(path, expected_story_id="river", expected_sha256=saved.sha256)
    s = step(s, "start_chapter", {"chapter_id": "c02"})
    s = step(s, "set_plan", {"artifact": artifact(json.dumps(PLAN, ensure_ascii=False), "current-plan")})
    s = step(s, "accept_plan", {"confirmation": confirmation(s, "plan")})
    kwargs = {"expected_disk_revision": revision, "expected_disk_sha256": sha(path)} if path.exists() else {}
    protocol.save_state(path, s, **kwargs)
    return path


def restore(path, *, revision=1):
    return writing.restore_source(path, expected_story_id="river", expected_revision=revision, expected_sha256=sha(path))


def flow(monkeypatch, handler=None, *, limits=None):
    calls = []
    reviews = 0
    def serve(request):
        nonlocal reviews
        calls.append(request)
        if handler:
            supplied = handler(request, len(calls))
            if supplied is not None: return supplied
        data = json.loads(request.content)
        system = data["messages"][0]["content"]
        if "严苛的网络小说章节编辑" in system:
            reviews += 1
            text = json.dumps({"verdict": "revise" if reviews == 1 else "pass", "issues": []})
        else: text = NEW
        return httpx.Response(200, json={"choices": [{"message": {"content": text}, "finish_reason": "stop"}]})
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(serve)))
    session = BudgetedWritingSession(RouterConfig(local=ProviderConfig("https://writer.invalid", "w"), reviewer=ProviderConfig("https://reviewer.invalid", "r")), limits=limits)
    return session, calls


def test_revision_zero_is_explicitly_unsupported_before_dispatch(tmp_path, monkeypatch):
    source = restore(make_archive(tmp_path, revision=0), revision=0)
    native = protocol.rebuild_accepted_history(source.state)["accepted_history_sha256"]
    session, calls = flow(monkeypatch)
    with pytest.raises(writing.ArchiveError, match="first|accepted|continu"):
        writing.prepare_accepted_context(source, current_chapter_id="c02", expected_history_sha256=native)
    with pytest.raises(writing.ArchiveError, match="first|accepted|continu"):
        session.run_from_accepted_archive(source, current_chapter_id="c02", review=False)
    assert calls == []


@pytest.mark.parametrize("names", [["薛遥", "薛遥"], [" 薛遥"], ["薛遥 "], [""]])
def test_ambiguous_current_character_names_do_not_dispatch(tmp_path, monkeypatch, names):
    path = make_archive(tmp_path, characters=[{"name": name} for name in names])
    session, calls = flow(monkeypatch)
    with pytest.raises(ValueError): session.run_from_accepted_archive(restore(path), current_chapter_id="c02", review=False)
    assert calls == []


@pytest.mark.parametrize("field", ["draft", "plan", "review", "voice", "diagnostics", "evidence", "other_source"])
def test_completed_candidate_binding_refuses_nested_replacement(tmp_path, monkeypatch, field):
    path = make_archive(tmp_path)
    session, calls = flow(monkeypatch)
    result = session.run_from_accepted_archive(restore(path), current_chapter_id="c02", review=True)
    if field == "draft": result.result.draft += " 被替换的文本。"
    elif field == "plan": result.result.plan.scenes[0].choice = "未经确认的新选择"
    elif field == "review": result.result.review.verdict = "pass"
    elif field == "voice": result.result.voice_dna_report["final"]["baseline"]["薛遥"]["line_count"] = 999
    elif field == "diagnostics": result.result.ai_flavor["forged"] = True
    elif field == "evidence":
        report = result.report(); report["budget_after"]["requests_reserved"] = 0
        object.__setattr__(result, "_evidence_json", json.dumps(report).encode())
    else:
        other = tmp_path / "other"; other.mkdir()
        object.__setattr__(result, "_source", restore(make_archive(other)))
    with pytest.raises(ValueError): result.report()
    with pytest.raises(ValueError): _ = result.final_text


@pytest.mark.parametrize("kind", ["journal", "owned_projection", "unsaved_receipt", "wrong_story", "wrong_revision", "wrong_hash"])
def test_restore_authority_failures_do_not_start_transport(tmp_path, monkeypatch, kind):
    path = make_archive(tmp_path)
    session, calls = flow(monkeypatch)
    expected = {"expected_story_id": "river", "expected_revision": 1, "expected_sha256": sha(path)}
    if kind in {"journal", "owned_projection", "unsaved_receipt"}:
        raw = json.loads(path.read_text())
        if kind == "journal": raw["engine_version"] = "gpt-author-journal-v1"
        elif kind == "owned_projection": raw["journal_owner"] = {"id": "separate-owner"}
        else: raw["write_receipt"] = {"status": "not_available"}
        path.write_text(json.dumps(raw, ensure_ascii=False))
        expected["expected_sha256"] = sha(path)
    elif kind == "wrong_story": expected["expected_story_id"] = "other"
    elif kind == "wrong_revision": expected["expected_revision"] = 0
    else: expected["expected_sha256"] = "f" * 64
    before = path.read_bytes()
    with pytest.raises(ValueError):
        source = writing.restore_source(path, **expected)
        session.run_from_accepted_archive(source, current_chapter_id="c02")
    assert calls == [] and path.read_bytes() == before


@pytest.mark.parametrize("kind", ["unknown_option", "review_hook", "extractor", "reviewer", "provider"])
def test_adapter_does_not_admit_external_execution_paths(tmp_path, monkeypatch, kind):
    path = make_archive(tmp_path)
    session, calls = flow(monkeypatch)
    key = {"unknown_option": "request_guard", "review_hook": "external_review_hooks", "extractor": "structured_extractor", "reviewer": "reviewer", "provider": "writer_provider"}[kind]
    with pytest.raises((TypeError, ValueError)):
        session.run_from_accepted_archive(restore(path), current_chapter_id="c02", **{key: lambda *args: (_ for _ in ()).throw(AssertionError("external execution"))})
    assert calls == []


def test_historical_nonjson_plan_stays_explicitly_unparsed_without_affecting_current_plan(tmp_path, monkeypatch):
    path = make_archive(tmp_path, historical_plan="作者以前确认的叙事计划，不是结构化 JSON。")
    session, calls = flow(monkeypatch)
    result = session.run_from_accepted_archive(restore(path), current_chapter_id="c02", review=False)
    assert result.report()["unparsed_historical_plans"] == ["c01"]
    assert result.result.final_report["voice"]["baseline"]["薛遥"]["line_count"] == 2
    assert "作者以前确认的叙事计划" in calls[0].content.decode()


def test_new_draft_omission_keeps_pr51_default_plan_binding_condition(tmp_path):
    path = make_archive(tmp_path)
    original = protocol.load_state(path, expected_story_id="river")
    drafted = step(original, "set_draft", {"artifact": artifact("保留的待确认草稿", "pending")})
    plain = protocol.preflight_context(drafted, [], 200000)
    omitted = protocol.preflight_context(drafted, [], 200000, include_current_draft=False)
    assert "保留的待确认草稿" in plain["context_text"]
    assert "保留的待确认草稿" not in omitted["context_text"]
    replanned = step(drafted, "set_plan", {"artifact": artifact(json.dumps(PLAN), "replacement")})
    assert "保留的待确认草稿" not in protocol.preflight_context(replanned, [], 200000)["context_text"]
    assert replanned.progress.draft.text == "保留的待确认草稿"


def test_returned_reports_and_source_models_are_detached(tmp_path, monkeypatch):
    path = make_archive(tmp_path); source = restore(path)
    before = path.read_bytes()
    preview = writing.prepare_accepted_context(source, current_chapter_id="c02")
    preview["history"]["accepted_chapters"][0]["voice_dna"].clear()
    preview["source"]["file_sha256"] = "0" * 64
    source.state.canon["characters"][0]["custom_voice"]["cadence"].append("changed")
    session, calls = flow(monkeypatch)
    result = session.run_from_accepted_archive(source, current_chapter_id="c02", review=False)
    report = result.report(); report["history_chapter_ids"].clear()
    assert result.report()["history_chapter_ids"] == ["c01"]
    assert path.read_bytes() == before
    assert "changed" not in calls[0].content.decode()


def test_guarded_provider_views_share_allowance_and_reject_rebinding(monkeypatch):
    sends = []
    original = httpx.Client
    def handler(request):
        sends.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "合成输出"}, "finish_reason": "stop"}]})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    budget = RequestBudget(RequestBudgetLimits(max_requests=1))
    base = OpenAICompatibleProvider(ProviderConfig("https://test.invalid", "m"), request_budget=budget)
    checks = []
    view = base.guarded(lambda: checks.append("checked"))
    assert view.request_budget is base.request_budget
    with pytest.raises(ValueError): view.guarded(lambda: None)
    messages = [{"role": "user", "content": "合成输入"}]
    assert view.chat(messages) == "合成输出"
    assert checks == ["checked", "checked"]
    with pytest.raises(ValueError): base.chat(messages)
    assert len(sends) == 1


@pytest.mark.parametrize("when", ["before", "after"])
def test_guard_failure_preserves_attempt_admission_semantics(monkeypatch, when):
    sent = []
    checks = []
    def guard():
        checks.append(1)
        if len(checks) == (1 if when == "before" else 2): raise ValueError("synthetic stale source")
    original = httpx.Client
    def handler(request):
        sent.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "输出"}, "finish_reason": "stop"}]})
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    budget = RequestBudget()
    base = OpenAICompatibleProvider(ProviderConfig("https://test.invalid", "m"), request_budget=budget)
    with pytest.raises(ValueError, match="stale"):
        base.guarded(guard).chat([{"role": "user", "content": "输入"}])
    assert len(sent) == budget.snapshot()["requests_reserved"] == (0 if when == "before" else 1)
    if sent: assert budget.snapshot()["attempts"][-1]["status"] == "failed"


def test_whole_wire_exact_boundary_and_one_byte_short(tmp_path, monkeypatch):
    path = make_archive(tmp_path); source = restore(path); before = path.read_bytes()
    session, calls = flow(monkeypatch)
    session.run_from_accepted_archive(source, current_chapter_id="c02", review=False)
    size = len(calls[0].content)
    # Undo the first transport patch before installing the next test transport.
    monkeypatch.undo()
    exact, exact_calls = flow(monkeypatch, limits=RequestBudgetLimits(max_request_bytes=size, max_total_request_bytes=size))
    result = exact.run_from_accepted_archive(source, current_chapter_id="c02", review=False)
    assert result.final_text and len(exact_calls[0].content) == size
    monkeypatch.undo()
    short, short_calls = flow(monkeypatch, limits=RequestBudgetLimits(max_request_bytes=size - 1))
    with pytest.raises(ValueError): short.run_from_accepted_archive(source, current_chapter_id="c02", review=False)
    assert short_calls == [] and short.budget_snapshot()["requests_reserved"] == 0
    assert path.read_bytes() == before


@pytest.mark.parametrize("path_change", ["unlink", "replace", "symlink"])
def test_disappeared_or_switched_archive_refuses_before_transport(tmp_path, monkeypatch, path_change):
    path = make_archive(tmp_path); source = restore(path)
    original_bytes = path.read_bytes()
    if path_change == "unlink": path.unlink()
    elif path_change == "replace": path.write_bytes(original_bytes + b" ")
    else:
        destination = tmp_path / "other.json"; destination.write_bytes(original_bytes)
        path.unlink(); path.symlink_to(destination)
    session, calls = flow(monkeypatch)
    with pytest.raises((ValueError, OSError)):
        session.run_from_accepted_archive(source, current_chapter_id="c02", review=False)
    assert calls == [] and session.budget_snapshot()["requests_reserved"] == 0


def test_archive_view_never_runs_unrelated_project_recovery_or_memory_write(tmp_path, monkeypatch):
    path = make_archive(tmp_path); source = restore(path)
    sentinels = {
        ".extraction-transaction.json": '{"must_remain":"legacy-pending"}',
        ".memory-commit-transaction.json": '{"must_remain":"separate-memory-pending"}',
        "characters.json": '[{"name":"Untouched"}]',
    }
    for name, content in sentinels.items(): (tmp_path / name).write_text(content)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    session, calls = flow(monkeypatch)
    result = session.run_from_accepted_archive(source, current_chapter_id="c02", review=False)
    assert result.report()["author_acceptance"].startswith("pending")
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before


@pytest.mark.parametrize("owned", ["writer", "reviewer"])
def test_changed_provider_config_refuses_before_any_dispatch(tmp_path, monkeypatch, owned):
    from novel_ai.orchestration import TaskKind
    path = make_archive(tmp_path); source = restore(path)
    session, calls = flow(monkeypatch)
    target = session._router.provider_for(TaskKind.DRAFT if owned == "writer" else TaskKind.REVIEW).provider
    target.config.base_url = "https://unapproved.invalid"
    with pytest.raises(ValueError, match="configuration changed"):
        session.run_from_accepted_archive(source, current_chapter_id="c02", review=True)
    assert calls == [] and session.budget_snapshot()["requests_reserved"] == 0


@pytest.mark.parametrize("invalid", [True, 1, "true", None])
def test_current_draft_omission_flag_requires_boolean(invalid, tmp_path):
    source = restore(make_archive(tmp_path))
    if invalid is True:
        # The actual boolean default remains supported and compatibility-safe.
        assert not protocol.preflight_next_chapter_context(source.state, [], 200000, include_current_draft=invalid)["blocked"]
    else:
        with pytest.raises(ValueError):
            protocol.preflight_next_chapter_context(source.state, [], 200000, include_current_draft=invalid)


def test_raw_custom_canon_and_declared_style_survive_all_four_wire_stages(tmp_path, monkeypatch):
    markers = ["CUSTOM_BIBLE_EXTENSION", "CUSTOM_CANON_EXTENSION", "CUSTOM_CHARACTER_VOICE", "CUSTOM_PROFILE_RHYTHM", "CUSTOM_GENRE_PROFILE"]
    path = make_archive(tmp_path,
        characters=[{"name": "薛遥", "knows": ["铃声来自渡口"], "aliases": ["小遥"], "custom_voice": {"cadence": [markers[2]]}}],
        canon_extra={"story_bible": {"title": "归铃", "genre": markers[4], "unknown_field": {"instruction_data": markers[0]}}, "custom_truth": {"preserve": [markers[1]]}},
        style={"genre_profile": markers[4], "custom_style": {"pace": markers[3], "allowed_restraint": True}})
    before = path.read_bytes()
    session, calls = flow(monkeypatch)
    result = session.run_from_accepted_archive(restore(path), current_chapter_id="c02", auto_repair=True)
    assert len(calls) == 4 and result.final_text
    for request in calls:
        body = request.content.decode()
        assert all(marker in body for marker in markers)
    assert "declared_style_card_in_current_accepted_plan_context" in calls[0].content.decode()
    assert "not supplied by this adapter" in calls[0].content.decode()
    assert path.read_bytes() == before


@pytest.mark.parametrize("field", ["genre", "style", "plan_source"])
@pytest.mark.parametrize("stage", [0, 2, 4])
def test_profile_and_accepted_plan_identity_changes_invalidate_old_source(tmp_path, monkeypatch, field, stage):
    path = make_archive(tmp_path, canon_extra={"story_bible": {"genre": "初始类型"}})
    source = restore(path)
    changed_bytes = []
    def change():
        payload = json.loads(path.read_text())
        if field == "genre": payload["canon"]["story_bible"]["genre"] = "作者的新类型"
        elif field == "style": payload["style_profile"]["custom_style"]["pace"] = "作者的新节奏"
        else: payload["progress"]["plan"]["source"]["location"] = "private://synthetic/rebound-plan"
        content = json.dumps(payload, ensure_ascii=False).encode()
        path.write_bytes(content)
        changed_bytes.append(content)
    if stage == 0: change()
    def handler(request, count):
        if count == stage: change()
    session, calls = flow(monkeypatch, handler)
    with pytest.raises(ValueError, match="archive"):
        session.run_from_accepted_archive(source, current_chapter_id="c02", auto_repair=True)
    assert len(calls) == stage
    assert path.read_bytes() == changed_bytes[0]
    assert session.budget_snapshot()["requests_reserved"] == stage
    if stage: assert session.budget_snapshot()["attempts"][-1]["status"] == "failed"


@pytest.mark.parametrize("target", ["c01", "c03", "", True])
def test_only_exact_current_unaccepted_chapter_may_dispatch(tmp_path, monkeypatch, target):
    path = make_archive(tmp_path)
    session, calls = flow(monkeypatch)
    with pytest.raises(ValueError): session.run_from_accepted_archive(restore(path), current_chapter_id=target, review=False)
    assert calls == []


def test_replacing_current_plan_requires_fresh_explicit_acceptance_before_writing(tmp_path, monkeypatch):
    path = make_archive(tmp_path)
    value = protocol.load_state(path, expected_story_id="river")
    replacement = deepcopy(PLAN); replacement["scenes"][0]["choice"] = "去另一座渡口"
    value = step(value, "set_plan", {"artifact": artifact(json.dumps(replacement, ensure_ascii=False), "unaccepted-replan")})
    protocol.save_state(path, value, expected_disk_revision=1, expected_disk_sha256=sha(path))
    session, calls = flow(monkeypatch)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="accepted plan|ready_to_draft"):
        session.run_from_accepted_archive(restore(path), current_chapter_id="c02", review=False)
    assert calls == [] and path.read_bytes() == before
