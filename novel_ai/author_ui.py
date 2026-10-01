"""Local author controls joining existing outline, market and release modules.

Rendering is deliberately provider-free. Only the existing chapter buttons call
models; importing outlines, scoring and packaging never create remote requests.
"""
from __future__ import annotations

import streamlit as st

from .author_workflow import (
    chapter_plan_from_outline, load_author_corpus, list_author_chapter_ids, outline_chapter_context,
    release_bundle_bytes, save_release_bundle, outline_digest, load_saved_outline, require_saved_outline,
)
from .market_eval import aggregate_market_scores, market_scoring_csv, parse_market_scores
from .outline import HierarchicalOutline, validate_outline
from .outline_markdown import parse_markdown_outline
from .release_pack import MarketProfile, build_release_pack


def render_outline_editor(store, project: str, title: str, premise: str) -> None:
    if project != store.slugify(project):
        st.warning("层级大纲请使用规范且唯一的项目名：" + store.slugify(project))
        return
    with st.expander("层级大纲 · 全书 / 卷 / 情节线 / 章 / 场景", expanded=False):
        st.caption("已有总纲保留。Markdown 按 # 到 ##### 连续分层；先预览并保存，再载入某章。不会调用模型。")
        if st.button("重新读取已保存层级大纲", key="btn_reload_hierarchy"):
            try:
                current = load_saved_outline(store, project)
                st.session_state.hierarchy_data = current
                st.session_state.hierarchy_previous_node = None
                st.info("已读取当前已保存大纲；未保存 JSON 和待写计划仍保留。请重新载入章节并确认计划。")
            except (ValueError, TypeError, OSError) as exc:
                st.error(str(exc))
        st.text_area("Markdown 层级大纲", key="hierarchy_markdown", height=220,
                     placeholder="# 全书\n## 第一卷\n### 主线\n#### 第一章\n本章承诺\n##### 场景一\n场景目标与作者备注")
        if st.button("解析 Markdown 为可编辑大纲", key="btn_parse_hierarchy"):
            try:
                parsed = parse_markdown_outline(st.session_state.hierarchy_markdown, title=title, premise=premise)
                st.session_state.hierarchy_editor = parsed.model_dump_json(indent=2)
                st.success("已解析；请检查下方 JSON，保存后生效。")
            except (ValueError, TypeError) as exc:
                st.error(str(exc))
        st.text_area("结构化大纲 JSON（可编辑）", key="hierarchy_editor", height=260)
        if st.button("保存层级大纲", key="btn_save_hierarchy"):
            try:
                parsed = validate_outline(HierarchicalOutline.model_validate_json(st.session_state.hierarchy_editor))
                with store._guard(project):
                    actual = store.read_json(project, "memory/hierarchical_outline.json")
                    expected = st.session_state.get("hierarchy_data")
                    if ((actual is None) != (expected is None)
                            or (actual is not None and outline_digest(actual) != outline_digest(expected))):
                        raise ValueError("层级大纲已被其他会话更新；未保存编辑已保留，请先重新读取并核对，原文件未覆盖。")
                    store.write_json(project, "memory/hierarchical_outline.json", parsed.model_dump())
                st.session_state.hierarchy_data = parsed.model_dump()
                st.success("层级大纲已保存；重新启动仍可选择章节。")
            except (ValueError, TypeError, OSError) as exc:
                st.error(str(exc))
        data = st.session_state.get("hierarchy_data")
        if not data:
            return
        try:
            outline = validate_outline(HierarchicalOutline.model_validate(data))
            chapters = {node.id: node for node in outline.flatten() if node.level == "chapter"}
            if not chapters:
                st.info("已保存大纲，但还没有 chapter 层级；可继续编辑。")
                return
            if st.session_state.get("hierarchy_selected") not in chapters:
                st.session_state.hierarchy_selected = next(iter(chapters))
            selected = st.selectbox("选择大纲章节", list(chapters), key="hierarchy_selected",
                                    format_func=lambda value: chapters[value].title + " · " + value)
            if st.session_state.get("hierarchy_previous_node") != selected:
                st.session_state.hierarchy_target_id = str(chapters[selected].metadata.get("chapter_id") or store.slugify(selected))
                st.session_state.hierarchy_previous_node = selected
            st.text_input("本章保存编号（可改为 001、002 等）", key="hierarchy_target_id")
            if st.button("载入本章到写作工作台", key="btn_load_hierarchy"):
                require_saved_outline(store, project, outline_digest(data))
                plan = chapter_plan_from_outline(outline, selected)
                node = chapters[selected]
                chapter_id = st.session_state.hierarchy_target_id
                st.session_state.chapter_id = chapter_id
                st.session_state.allow_chapter_overwrite = False
                st.session_state.overwrite_chapter_binding = chapter_id
                st.session_state.chapter_goal = plan.chapter_promise or node.title
                st.session_state.pending_plan_json = plan.model_dump_json(indent=2)
                st.session_state.plan_new = True
                st.session_state.pending_plan_meta = {
                    "project": project, "chapter_id": chapter_id,
                    "outline_node_id": selected, "outline_sha256": outline_digest(data),
                    "outline_context": outline_chapter_context(outline, selected),
                }
                st.session_state.last_result = None
                st.session_state.last_result_meta = {}
                st.session_state.last_extraction = None
                st.session_state.last_self_similarity = []
                st.session_state.last_overlap = 0.0
                st.success("已载入“章节写作”。可先生成完整场景计划，或编辑并补齐场景因果字段后写正文。")
        except (ValueError, TypeError, KeyError) as exc:
            st.error(str(exc))


def render_release_workbench(store, project: str) -> None:
    if project != store.slugify(project):
        st.warning("市场审阅请使用规范且唯一的项目名：" + store.slugify(project))
        return
    st.subheader("已保存章节 → 人工市场审阅 → 本地发布候选包")
    st.caption("所有材料在本地处理。候选包包含原创正文；下载后请自行决定交给谁，不会自动上传或提交到平台。")
    try:
        available = list_author_chapter_ids(store, project)
    except (ValueError, OSError) as exc:
        st.error(str(exc))
        return
    st.write("已保存的章节 ID：" + ("、".join(available) if available else "暂无"))
    st.selectbox("审阅阶段", ["opening_3", "retention_20"], key="release_stage",
                 format_func=lambda value: "前三章" if value == "opening_3" else "前 20 章")
    st.text_area("作者确认的章节顺序（每行一个 ID）", key="release_chapter_order", height=100,
                 help="请按实际开篇顺序填写恰好 3 或 20 章；系统不会把文件名字母顺序当成章序，也无法证明任意选择就是实际开篇。")
    left, right = st.columns(2)
    with left:
        st.text_input("发布候选书名", key="release_title")
        st.text_input("目标平台", key="release_platform")
        st.text_input("发布题材", key="release_genre")
        st.text_input("目标读者", key="release_audience")
    with right:
        st.text_input("一句话看点", key="release_hook")
        st.text_input("更新节奏（作者计划）", key="release_cadence")
        st.text_area("标签（每行一个）", key="release_tags", height=80)
    st.text_area("短简介", key="release_blurb", height=100)
    st.text_area("长简介（可选）", key="release_long_blurb", height=100)
    st.text_area("待人工核查事项（每行一个）", key="release_checks", height=100)
    st.text_area("人工评分 CSV（粘贴填写后的完整表）", key="release_scores_text", height=180)
    st.caption("空表不会产生分数。10 项完整评分绑定正文、章序、题材和读者；换稿或换读者后须重新审阅。分数不代表平台认可或可发布结论。")
    fields = (
        "release_stage", "release_chapter_order", "release_title", "release_platform",
        "release_genre", "release_audience", "release_hook", "release_cadence",
        "release_tags", "release_blurb", "release_long_blurb", "release_checks", "release_scores_text",
    )
    if st.button("保存审阅与发布草案", key="btn_save_release_draft"):
        try:
            store.write_json(project, "memory/release_workspace.json", {key: st.session_state[key] for key in fields})
            st.success("草案已保存。草案保存不等于通过审阅。")
        except OSError as exc:
            st.error(str(exc))
    chapter_ids = [item.strip() for item in st.session_state.release_chapter_order.splitlines() if item.strip()]
    try:
        corpus = load_author_corpus(
            store, project, chapter_ids, st.session_state.release_stage,
            audience=st.session_state.release_audience.strip(), genre=st.session_state.release_genre.strip(),
        )
    except (ValueError, TypeError, OSError) as exc:
        st.info("准备审阅语料：" + str(exc))
        return
    st.caption("本次语料指纹：" + corpus.fingerprint())
    st.download_button("下载空白人工评分表", market_scoring_csv(corpus).encode("utf-8-sig"),
                       file_name="market_scoring.csv", mime="text/csv", key="download_market_sheet")
    scores = None
    if st.session_state.release_scores_text.strip():
        try:
            scores = parse_market_scores(st.session_state.release_scores_text, corpus)
            st.json(aggregate_market_scores(scores))
        except (ValueError, TypeError) as exc:
            st.error("评分不能用于当前候选包：" + str(exc))
            return
    else:
        st.info("尚未完成独立人工市场审阅；候选包会明确保留这一状态。")
    try:
        tags = [line.strip() for line in st.session_state.release_tags.splitlines() if line.strip()]
        pack = build_release_pack(
            corpus,
            MarketProfile(platform=st.session_state.release_platform, genre=st.session_state.release_genre,
                          audience=st.session_state.release_audience, comparable_tags=tags,
                          cadence=st.session_state.release_cadence),
            title=st.session_state.release_title, one_line_hook=st.session_state.release_hook,
            short_blurb=st.session_state.release_blurb, long_blurb=st.session_state.release_long_blurb,
            tags=tags, manual_checks=st.session_state.release_checks.splitlines(),
        )
        data = st.session_state.get("hierarchy_data")
        outline = validate_outline(HierarchicalOutline.model_validate(data)) if data else None
        bundle = release_bundle_bytes(corpus, pack, chapter_ids=chapter_ids, scores=scores, outline=outline)
    except (ValueError, TypeError) as exc:
        st.info("补齐发布草案后即可生成候选包：" + str(exc))
        return
    st.download_button("下载本地发布候选包 ZIP", bundle, file_name="novel-release-candidate.zip",
                       mime="application/zip", key="download_release_bundle")
    if st.button("保存候选包到项目 exports", key="btn_save_release_bundle"):
        try:
            target = save_release_bundle(store, project, bundle)
            st.success("已保存 " + target.name + "；重复保存相同内容复用原文件。")
        except (ValueError, OSError) as exc:
            st.error(str(exc))
