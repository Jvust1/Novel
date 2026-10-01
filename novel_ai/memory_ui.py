"""Optional workbench view for explicit version-bound memory acceptance."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .author_workflow import chapter_revision_matches
from .memory_proposals import (
    MemoryProposal, apply_memory_proposal, author_context, capture_memory_source,
    extract_memory_proposal, list_memory_proposals, load_memory_proposal, save_memory_proposal,
    memory_proposal_receipt,
)
from .models import StoryBible


def _result_binding(result):
    if result is None:
        return None
    try:
        return {"text_sha256": hashlib.sha256((result.final_text.strip() + "\n").encode()).hexdigest(),
                "plan": result.plan.model_dump()}
    except (ValueError, TypeError, AttributeError):
        return {"invalid": True}


def _view_binding(state, project, chapter_id):
    return json.loads(json.dumps({"project": state.get("project_name", project),
        "chapter_id": state.get("chapter_id", chapter_id), "result": _result_binding(state.get("last_result")),
        "meta": state.get("last_result_meta", {}), "displayed_text_sha256": state.get("memory_displayed_text_sha256")},
        ensure_ascii=False, allow_nan=False))


def workbench_memory_context(state) -> dict[str, Any]:
    """Read live widget state rather than closed-over pre-request local values."""
    def lines(key):
        value = state.get(key, "")
        if not isinstance(value, str):
            raise ValueError("author text field has an unsupported value")
        return [x.strip() for x in value.splitlines() if x.strip()]
    saved_bible = state.get("memory_source_bible", {})
    bible = StoryBible(title=state.get("title", ""), genre=state.get("genre", ""),
        audience=saved_bible.get("audience", ""),
        tone=state.get("tone", ""), premise=state.get("premise", ""), themes=lines("themes_text"),
        world_rules=lines("rules_text"), locked_facts=lines("locked_text"), forbidden_moves=lines("forbidden_text"))
    style = state.get("style")
    if hasattr(style, "model_dump"):
        style = style.model_dump()
    return author_context(bible={**saved_bible, **bible.model_dump()}, characters=state.get("characters", []),
        extra={"outline": state.get("outline", ""), "style": style,
               "hierarchy": state.get("hierarchy_data"), "reference_hashes": sorted(state.get("reference_hashes", []))})


def render_memory_proposals(st, store, project: str, chapter_id: str, result, engine_factory) -> None:
    st.divider()
    st.subheader("章节后处理 · 记忆候选与作者确认")
    st.caption("先提取并查看候选；只有你分别确认这版正文和记忆变更，才写入正式记忆。模型审校通过和保存草稿都不代替接受。")
    st.caption("单次提取使用独立请求额度：至多 2 次发送含格式回退，完整输入单次 512 KiB、累计 1 MiB；超额会停止而不截断。")
    state = st.session_state
    original_view = _view_binding(state, project, chapter_id)

    def ensure_view():
        if (original_view["project"] != project or original_view["chapter_id"] != chapter_id
                or original_view["result"] != _result_binding(result)
                or _view_binding(state, project, chapter_id) != original_view):
            raise ValueError("writing selection or displayed result changed; no old-view publication is allowed")

    def live():
        ensure_view()
        return workbench_memory_context(state)

    meta = state.get("last_result_meta", {})
    matches = bool(result is not None and meta.get("project") == project
        and meta.get("chapter_id") == chapter_id and meta.get("text_sha256")
        and chapter_revision_matches(store, project, chapter_id, meta["text_sha256"]))
    if state.get("memory_displayed_text_sha256") is not None:
        matches = matches and state.memory_displayed_text_sha256 == meta.get("text_sha256")
    if result is not None:
        try:
            matches = matches and hashlib.sha256((result.final_text.strip() + "\n").encode()).hexdigest() == meta.get("text_sha256")
        except (ValueError, TypeError):
            matches = False
    if result is not None and not matches:
        st.warning("当前显示的是另一章、没有已保存的版本绑定，或正文发生变化。请核对原章节与文本版本后再提取记忆候选。")
    if st.button("提取本章记忆候选 不回写", key="btn_memory_propose", use_container_width=True, disabled=not matches):
        try:
            context = live()
            source = capture_memory_source(store, project, chapter_id, final_text=result.final_text,
                                           plan=result.plan, context=context)
            proposal = extract_memory_proposal(store, source, engine_factory(), context=context, current_context=live)
            save_memory_proposal(store, proposal, context=live())
            ensure_view()
            state.memory_candidate_json = proposal._serialized
            state.last_memory_commit = None
            st.success("记忆候选已保存，正式人物和故事状态未改变。请先查看，再分别确认。")
        except Exception as exc:
            st.exception(exc)

    try:
        ids = list_memory_proposals(store, project, chapter_id)
        if ids:
            selected = st.selectbox("本章已保存的记忆候选", ids, key="memory_candidate_choice")
            if st.button("载入待确认记忆候选", key="btn_memory_load"):
                ensure_view()
                state.memory_candidate_json = load_memory_proposal(store, project, selected)._serialized
                state.last_memory_commit = None
    except (ValueError, OSError) as exc:
        st.warning("待确认候选暂不可载入，请保留原件并核对：" + str(exc))

    raw = state.get("memory_candidate_json")
    if not raw:
        st.info("尚无本章待确认记忆；已有候选可以从上方载入，不需要重新调用模型。")
        return
    try:
        proposal = MemoryProposal(raw)
        data = proposal.to_dict()
        if data["source"]["project"] != project or data["source"]["chapter_id"] != chapter_id:
            st.info("所选章节与当前候选不同；旧候选保留在原章节中，不会跨章回写。")
            return
        preview = proposal.preview()
        historical_receipt = memory_proposal_receipt(store, proposal)
        if historical_receipt is not None:
            ensure_view()
            current_cards = store.read_json(project, "memory/characters.json", [])
            ensure_view()
            pending_readback = state.get("memory_ui_readback_pending")
            if (isinstance(pending_readback, dict) and pending_readback.get("proposal_id") == proposal.proposal_id
                    and pending_readback.get("context") == live()):
                state.characters = current_cards
                state.memory_ui_readback_pending = None
            elif state.get("characters", []) != current_cards:
                st.warning("这份记忆已有提交回执，但当前界面人物与已保存版本不同；未覆盖未保存编辑。请先核对或明确重新载入。")
                if st.button("重新载入当前已保存人物", key="btn_memory_reload_cards"):
                    ensure_view()
                    state.characters = current_cards
                    state.memory_ui_readback_pending = None
            state.last_memory_commit = historical_receipt
            if not chapter_revision_matches(store, project, chapter_id, preview["source_text_sha256"]):
                st.warning("这是已经提交的历史版本；磁盘正文随后发生变化，旧接受记录不能认可新稿，需要历史修订对账。")
        st.caption("候选版本：" + proposal.proposal_id[-12:] + " · 正文 SHA256：" + preview["source_text_sha256"][:16])
        with st.expander("查看拟写入的人物 事实 时间线与伏笔", expanded=True):
            st.json(preview)
        with st.expander("核对候选绑定的正文与计划", expanded=False):
            st.json({"chapter_id": chapter_id, "source_text": data["source"]["inputs"][f"chapters/{chapter_id}.md"],
                     "source_plan": data["source"]["plan"]})
        displayed = _result_binding(state.get("last_result"))
        display_matches = (displayed is None or (displayed.get("text_sha256") == preview["source_text_sha256"]
                           and displayed.get("plan") == data["source"]["plan"]
                           and meta.get("project") == project and meta.get("chapter_id") == chapter_id))
        if state.get("memory_displayed_text_sha256") is not None:
            display_matches = display_matches and state.memory_displayed_text_sha256 == preview["source_text_sha256"]
        if not display_matches and historical_receipt is None:
            st.warning("显示中的正文或计划与该记忆候选不同，不能把旧候选的接受用于当前显示的新稿。请核对版本。")
        ack_text = st.checkbox("我接受这一版正文作为记忆来源", value=False, key="memory_text_" + proposal.proposal_id)
        ack_memory = st.checkbox("我已查看并接受这份记忆变更", value=False, key="memory_changes_" + proposal.proposal_id)
        done = historical_receipt is not None
        if st.button("确认并写入这份记忆", key="btn_memory_apply", type="primary",
                     use_container_width=True, disabled=not (ack_text and ack_memory and display_matches) or done):
            context = live()
            if state.get("memory_candidate_json") != proposal._serialized:
                raise ValueError("the displayed memory candidate changed before confirmation")
            state.memory_ui_readback_pending = {"proposal_id": proposal.proposal_id, "context": context}
            receipt = apply_memory_proposal(store, proposal, context=context,
                chapter_accepted=ack_text, memory_accepted=ack_memory,
                confirmation_source="explicit-workbench-memory-confirmation:" + proposal.proposal_id)
            # Only publish UI state after the committed files have read back.
            saved_cards = store.read_json(project, "memory/characters.json", [])
            ensure_view()
            if live() == context:
                state.characters = saved_cards
                state.memory_ui_readback_pending = None
            else:
                st.warning("记忆已提交；界面出现新的作者修改，未覆盖这些未保存编辑，请核对。")
            state.last_extraction = data["extraction"]
            state.last_memory_commit = receipt
            st.success("这版记忆已确认并提交，相关文件已读回；正文文件未改动。")
        elif done:
            st.success("这份记忆已经提交。生成时的模型审校报告仍独立保留，作者接受记录在本次提交回执中。")
    except Exception as exc:
        st.exception(exc)
