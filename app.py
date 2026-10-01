from __future__ import annotations

import json
import hashlib

import streamlit as st

from novel_ai.author_ui import outline_digest, render_outline_editor, render_release_workbench
from novel_ai.author_workflow import save_chapter_plan, validate_chapter_target, chapter_revision_matches, write_author_chapter
from novel_ai.workflow_guard import validate_plan_stage
from novel_ai.context import ContextAssembler
from novel_ai.project_session import switch_project
from novel_ai.engine import NovelEngine
from novel_ai.memory_ui import render_memory_proposals
from novel_ai.longform_tools import near_duplicate_chapters
from novel_ai.longform_analytics import trope_frequency, cluster_story_dna, project_story_dna_2d, detect_longform_drift, analytics_backend_capabilities
from novel_ai.models import Character, ChapterPlan, StoryBible, StyleFingerprint
from novel_ai.reading import extract_reference_text
from novel_ai.provider import OpenAICompatibleProvider, ProviderConfig
from novel_ai.request_budget import RequestBudget, RequestBudgetLimits
from novel_ai.quality_gate import analyze_prose_quality
from novel_ai.reference_similarity import analyze_reference_similarity
from novel_ai.release_eval import build_release_quality_snapshot
from novel_ai.recall_backends import recall_backend_capabilities
from novel_ai.experimental_backends import experimental_backend_matrix
from novel_ai.story_dna import story_structure_capabilities
from novel_ai.storage import ProjectStore
from novel_ai.style_engine import (
    analyze_style,
    blend_styles,
    build_reference_signature,
    detect_ai_flavor,
    reference_overlap,
)


st.set_page_config(page_title="Novel", page_icon="✍️", layout="wide")
st.title("Novel · AI 网络小说写作助手")
st.caption("情节与人物优先 · 大纲扩写 · 长篇记忆 · Style DNA · 去 AI 味审校")

store = ProjectStore("data")

if "characters" not in st.session_state:
    st.session_state.characters = []
if "style" not in st.session_state:
    st.session_state.style = None
if "style_profiles" not in st.session_state:
    st.session_state.style_profiles = []
if "reference_hashes" not in st.session_state:
    st.session_state.reference_hashes = set()
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_overlap" not in st.session_state:
    st.session_state.last_overlap = 0.0
if "last_extraction" not in st.session_state:
    st.session_state.last_extraction = None
if "last_self_similarity" not in st.session_state:
    st.session_state.last_self_similarity = []


with st.sidebar:
    st.header("模型连接")
    base_url = st.text_input("Base URL", placeholder="例如本地或云端 OpenAI-compatible endpoint")
    model = st.text_input("Model")
    api_key = st.text_input("API Key（只在当前会话使用）", type="password")
    st.caption("密钥不会由本应用写入项目文件。")
    with st.expander("可选 Recall 后端", expanded=False):
        st.json(recall_backend_capabilities())
    with st.expander("实验编排/记忆/优化后端", expanded=False):
        st.json(experimental_backend_matrix())
    with st.expander("Story DNA / 中文结构抽取后端", expanded=False):
        st.json(story_structure_capabilities())
    with st.expander("长篇分析后端", expanded=False):
        st.json(analytics_backend_capabilities())
    st.divider()
    project_name = st.text_input("当前项目", value="MyNovel", key="project_name")
    target_chars = st.number_input("目标章节字数", min_value=800, max_value=15000, value=3500, step=200)


def make_provider(*, request_budget: RequestBudget | None = None) -> OpenAICompatibleProvider:
    if not base_url.strip() or not model.strip():
        raise ValueError("请先填写 Base URL 和 Model")
    return OpenAICompatibleProvider(
        ProviderConfig(base_url=base_url.strip(), model=model.strip(), api_key=api_key.strip()),
        request_budget=request_budget,
    )


def style_from_state() -> StyleFingerprint | None:
    value = st.session_state.style
    if isinstance(value, StyleFingerprint):
        return value
    if isinstance(value, dict):
        return StyleFingerprint.model_validate(value)
    return None


def current_bible() -> StoryBible:
    return StoryBible(
        title=title,
        genre=genre,
        audience=st.session_state.get("memory_source_bible", {}).get("audience", ""),
        tone=tone,
        premise=premise,
        themes=[x.strip() for x in themes_text.splitlines() if x.strip()],
        world_rules=[x.strip() for x in rules_text.splitlines() if x.strip()],
        locked_facts=[x.strip() for x in locked_text.splitlines() if x.strip()],
        forbidden_moves=[x.strip() for x in forbidden_text.splitlines() if x.strip()],
    )


def seed_project_state() -> None:
    """Restore this project's persisted/cached state without crossing books."""
    switch_project(st.session_state, store, project_name)


seed_project_state()


story_tab, char_tab, style_tab, write_tab, review_tab, release_tab = st.tabs(
    ["📚 故事与大纲", "👥 人物", "🎛️ Style Lab", "✍️ 章节写作", "🔎 审校", "📦 市场审阅与发布"]
)

with story_tab:
    st.caption("设定、人物与 Style 会随保存写入本地项目目录；重启应用或切换项目时自动回载。")
    col1, col2 = st.columns(2)
    with col1:
        title = st.text_input("书名", key="title")
        genre = st.text_input("题材", key="genre", placeholder="都市 / 玄幻 / 悬疑 / 言情 / 科幻……")
        tone = st.text_input("基调", key="tone", placeholder="克制、冷幽默、压迫、热血……")
        premise = st.text_area("核心设定 / Premise", height=130, key="premise")
    with col2:
        themes_text = st.text_area("主题（每行一个）", height=100, key="themes_text")
        rules_text = st.text_area("世界规则（每行一个）", height=130, key="rules_text")
        locked_text = st.text_area("锁定事实（每行一个，不与世界规则混写）", height=100, key="locked_text")
        forbidden_text = st.text_area("明确禁止的剧情处理（每行一个）", height=100, key="forbidden_text")

    outline = st.text_area("总纲 / 卷纲 / 上层大纲", height=280, key="outline")
    if st.button("保存故事设定到本地", use_container_width=True):
        bible = current_bible()
        saved_bible = {**st.session_state.get("memory_source_bible", {}), **bible.model_dump()}
        store.write_json(project_name, "memory/story_bible.json", saved_bible)
        st.session_state.memory_source_bible = saved_bible
        store.write_json(project_name, "memory/outline.json", {"outline": outline})
        st.success("已保存到本地 data/projects 目录。")
    render_outline_editor(store, project_name, title, premise)

with char_tab:
    st.subheader("人物动态状态")
    st.caption("人物不是静态简介。尤其要维护当前目标、秘密、知识边界、错误认知和关系变化。")

    with st.expander("新增人物", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            c_name = st.text_input("姓名", key="new_char_name")
            c_identity = st.text_input("身份", key="new_char_identity")
            c_desire = st.text_input("核心欲望", key="new_char_desire")
            c_goal = st.text_input("当前目标", key="new_char_goal")
            c_fear = st.text_input("恐惧 / 缺陷", key="new_char_fear")
        with c2:
            c_secret = st.text_input("秘密", key="new_char_secret")
            c_speech = st.text_input("说话方式", key="new_char_speech")
            c_knows = st.text_area("已经知道（每行一个）", key="new_char_knows", height=90)
            c_unknown = st.text_area("明确不知道（每行一个）", key="new_char_unknown", height=90)
        if st.button("添加人物"):
            if not c_name.strip():
                st.warning("人物至少需要姓名。")
            else:
                char = Character(
                    name=c_name.strip(),
                    identity=c_identity,
                    core_desire=c_desire,
                    current_goal=c_goal,
                    fear=c_fear,
                    secret=c_secret,
                    speech=c_speech,
                    knows=[x.strip() for x in c_knows.splitlines() if x.strip()],
                    does_not_know=[x.strip() for x in c_unknown.splitlines() if x.strip()],
                )
                st.session_state.characters.append(char.model_dump())
                st.success(f"已添加 {char.name}")

    if st.session_state.characters:
        st.dataframe(st.session_state.characters, use_container_width=True)
        names = [c["name"] for c in st.session_state.characters]
        locked_names = st.multiselect(
            "锁定人物（Product Spec：锁定后记忆回写不得擅改其人物卡）",
            options=names,
            default=[c["name"] for c in st.session_state.characters if c.get("locked")],
        )
        if st.button("应用锁定"):
            for c in st.session_state.characters:
                c["locked"] = c["name"] in locked_names
            store.write_json(project_name, "memory/characters.json", st.session_state.characters)
            st.success("锁定状态已应用并保存。")
        if st.button("保存人物到本地"):
            store.write_json(project_name, "memory/characters.json", st.session_state.characters)
            st.success("人物已保存。")
    else:
        st.info("还没有人物。")

with style_tab:
    st.subheader("Style Lab · 多来源文风 DNA")
    st.write(
        "每份代表文本先提取统计特征，再可选用模型抽象叙事距离、对白方式、情绪表达、环境进入方式等语义特征。"
        "多份 profile 按权重融合；参考正文不会写入 Style DNA 文件。"
    )

    uploaded = st.file_uploader("上传参考文本（支持 TXT / MD / DOCX / PDF）", type=["txt", "md", "docx", "pdf"])
    pasted_reference = st.text_area("或粘贴参考文本", height=220)
    reference_name = st.text_input("风格来源名称", value=f"Reference-{len(st.session_state.style_profiles) + 1}")
    weight = st.number_input("融合权重", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
    use_semantic = st.checkbox("使用当前模型做语义文体分析", value=True)
    semantic_notes = st.text_area(
        "人工补充风格备注（可选）",
        placeholder="例如：近距离第三人称；对白克制；环境多通过人物动作带出；情绪少直说……",
        height=100,
    )

    if st.button("分析并加入风格库", use_container_width=True):
        text = pasted_reference
        if uploaded is not None:
            text = extract_reference_text(uploaded.name, uploaded.getvalue())
        if len(text.strip()) < 300:
            st.warning("样本文本太短，建议至少提供 300 字；稳定分析最好使用更长样本。")
        else:
            try:
                fp = analyze_style(text, reference_name)
                if use_semantic:
                    engine = NovelEngine(make_provider())
                    fp = engine.enrich_style(text, fp)
                if semantic_notes.strip():
                    fp.custom_notes.extend([x.strip() for x in semantic_notes.splitlines() if x.strip()])

                signature = build_reference_signature(text)
                st.session_state.style_profiles.append(
                    {"name": reference_name, "weight": float(weight), "fingerprint": fp.model_dump()}
                )
                st.session_state.reference_hashes |= signature

                weighted = [
                    (StyleFingerprint.model_validate(item["fingerprint"]), float(item["weight"]))
                    for item in st.session_state.style_profiles
                ]
                composite = blend_styles(weighted, name="Novel-Composite")
                st.session_state.style = composite.model_dump()

                store.write_json(project_name, "styles/style_profiles.json", st.session_state.style_profiles)
                store.write_json(project_name, "styles/style_dna.json", composite.model_dump())
                store.write_json(
                    project_name,
                    "styles/reference_signature.json",
                    {"hashes": sorted(st.session_state.reference_hashes), "shingle_chars": 18},
                )
                st.success("已加入风格库并重新计算综合 Style DNA；参考正文未写入风格文件。")
            except Exception as exc:
                st.exception(exc)

    if st.session_state.style_profiles:
        st.markdown("#### 已加入的风格来源")
        st.dataframe(
            [{"name": p["name"], "weight": p["weight"]} for p in st.session_state.style_profiles],
            use_container_width=True,
        )
        if st.button("清空风格库"):
            st.session_state.style_profiles = []
            st.session_state.style = None
            st.session_state.reference_hashes = set()
            st.rerun()

    fp = style_from_state()
    if fp:
        st.markdown("#### 当前综合 Style DNA")
        st.json(fp.model_dump())

with write_tab:
    st.subheader("章纲 → 场景计划 → 正文")
    chapter_id = st.text_input("章节编号 / 名称", value="001", key="chapter_id")
    if st.session_state.get("overwrite_chapter_binding") != chapter_id:
        st.session_state.allow_chapter_overwrite = False
        st.session_state.overwrite_chapter_binding = chapter_id
    allow_overwrite = st.checkbox("允许覆盖此编号已有正文（请先保留备份）", key="allow_chapter_overwrite")
    chapter_goal = st.text_area(
        "本章章纲 / 目标",
        key="chapter_goal",
        placeholder="可以只有几句话。系统会先拆成场景，不会直接机械拉长。",
        height=180,
    )
    user_notes = st.text_area("本章额外要求", key="chapter_notes", placeholder="例如：本章不要揭晓真相；减少环境；最后停在门被推开……", height=100)
    mode = st.radio("生成模式", ["快速草稿", "标准审校", "精修"], horizontal=True, index=1)
    confirm_plan = st.checkbox(
        "写正文前确认/编辑场景计划（推荐）",
        value=True,
        help="North Star 原则：AI 先给结构化建议，作者可编辑后再生成正文，不被全自动流水线绑架。",
    )

    diverse_recall = st.checkbox(
        "多样化历史召回（实验）", value=False, key="diverse_recall",
        help="用本章目标匹配历史摘要，再减少重复线索；仅本地字符匹配，不下载模型。尚未证明提升写作质量。",
    )

    if "pending_plan_json" not in st.session_state:
        st.session_state.pending_plan_json = ""
    if "pending_plan_meta" not in st.session_state:
        st.session_state.pending_plan_meta = {}
    if "plan_new" not in st.session_state:
        st.session_state.plan_new = False

    def _validate_chapter_target():
        validate_chapter_target(store, project_name, chapter_id, allow_overwrite=allow_overwrite)

    def _plan_binding():
        meta = st.session_state.pending_plan_meta
        if meta.get("project", project_name) != project_name or meta.get("chapter_id", chapter_id) != chapter_id:
            raise ValueError("待确认计划属于另一章，请重新载入或生成本章计划。")
        if meta.get("outline_sha256") and meta["outline_sha256"] != outline_digest(st.session_state.get("hierarchy_data") or {}):
            raise ValueError("层级大纲已变化，请重新载入章节并确认计划。")
        return meta

    def _engine_and_inputs():
        engine = NovelEngine(make_provider())
        bible = current_bible()
        characters = [Character.model_validate(c) for c in st.session_state.characters]
        return engine, bible, characters

    col1, col2, col3 = st.columns(3)
    with col1:
        make_plan = st.button("① 生成场景计划", use_container_width=True, key="btn_plan")
    with col2:
        write_draft = st.button(
            "② 按计划写正文",
            type="primary",
            use_container_width=True,
            disabled=not st.session_state.pending_plan_json,
            key="btn_draft",
        )
    with col3:
        one_shot = st.button("一步生成", use_container_width=True, help="跳过计划确认：计划→正文→审校一次完成", key="btn_oneshot")

    if st.button("清空待写计划，开始新章", key="btn_clear_plan"):
        st.session_state.pending_plan_json = ""
        st.session_state.pending_plan_meta = {}
        st.session_state.plan_editor = ""
        st.session_state.plan_new = False
        st.session_state.last_result = None
        st.session_state.last_result_meta = {}
        st.session_state.last_extraction = None
        st.session_state.memory_candidate_json = None
        st.session_state.last_memory_commit = None
        st.session_state.last_self_similarity = []
        st.session_state.last_overlap = 0.0
        st.rerun()

    if make_plan:
        try:
            meta = _plan_binding()
            engine, bible, characters = _engine_and_inputs()
            context = ContextAssembler(store, project_name).assemble(
                recall_query=chapter_goal if diverse_recall else ""
            )
            planning_context = (context.prompt_sections() + "\n\n" + meta.get("outline_context", "")).strip()
            if meta.get("outline_node_id"):
                seed_json = st.session_state.get("plan_editor") or st.session_state.pending_plan_json
                seed = ChapterPlan.model_validate_json(seed_json)
                seed_json = seed.model_dump_json(indent=2)
                if len(seed_json) > 16000:
                    raise ValueError("作者场景计划超过本次规划上下文上限，请缩短本章计划后重试；未截断或丢弃场景。")
                planning_context += "\n\n作者当前可编辑场景计划（保留已明确的目标与选择，只补充缺失字段）：\n" + seed_json
            plan = engine.plan(
                bible, outline, chapter_goal, characters, context.recent_summaries, planning_context
            )
            st.session_state.pending_plan_json = plan.model_dump_json(indent=2)
            st.session_state.pending_plan_meta = {
                **meta, "project": project_name, "chapter_id": chapter_id,
                "recent": context.recent_summaries,
                "extra": context.prompt_sections(),
                "recall_report": context.recall_report,
            }
            st.session_state.plan_new = True
            st.rerun()
        except Exception as exc:
            st.exception(exc)

    if write_draft:
        try:
            _validate_chapter_target()
            meta = _plan_binding()
            plan_json = st.session_state.get("plan_editor") or st.session_state.pending_plan_json
            plan = ChapterPlan.model_validate(json.loads(plan_json))
            if meta.get("outline_node_id"):
                check = validate_plan_stage(plan)
                if not check.ok:
                    raise ValueError("请先补全场景计划：" + "；".join(check.issues))
            engine, bible, characters = _engine_and_inputs()
            context = ContextAssembler(store, project_name).assemble(recall_query=chapter_goal if diverse_recall else "")
            meta = {**meta, "recent": context.recent_summaries,
                    "extra": (context.prompt_sections() + "\n\n" + meta.get("outline_context", "")).strip()}
            result = engine.run_from_plan(
                bible=bible, plan=plan, characters=characters,
                recent_summaries=meta.get("recent", []), style=style_from_state(),
                target_chars=int(target_chars), user_notes=user_notes,
                review=mode != "快速草稿", auto_repair=mode == "精修",
                extra_context=meta.get("extra", ""), reference_hashes=st.session_state.reference_hashes,
                historical_story_dna=[row for row in store.load_story_dna_history(project_name)
                                      if str(row.get("chapter_id")) != chapter_id],
                historical_voice_dna=[row for row in store.load_voice_dna_history(project_name)
                                      if str(row.get("chapter_id")) != chapter_id],
            )
            final_text = result.final_text
            overlap = reference_overlap(final_text, st.session_state.reference_hashes)
            write_author_chapter(store, project_name, chapter_id, final_text, allow_overwrite=allow_overwrite)
            save_chapter_plan(store, project_name, chapter_id, plan, final_text)
            st.session_state.last_result = result
            st.session_state.last_overlap = overlap
            st.session_state.last_self_similarity = []
            st.session_state.last_result_meta = {
                "project": project_name, "chapter_id": chapter_id,
                "text_sha256": hashlib.sha256((final_text.strip() + "\n").encode("utf-8")).hexdigest(),
            }
            st.session_state.last_extraction = None
            st.session_state.memory_candidate_json = None
            st.session_state.last_memory_commit = None
            st.success("章节已按确认的计划生成并保存到本地项目目录。")
        except Exception as exc:
            st.exception(exc)

    if one_shot:
        try:
            _validate_chapter_target()
            meta = _plan_binding()
            engine, bible, characters = _engine_and_inputs()
            context = ContextAssembler(store, project_name).assemble(
                recall_query=chapter_goal if diverse_recall else ""
            )
            result = engine.run(
                bible=bible,
                outline=outline,
                chapter_goal=chapter_goal,
                characters=characters,
                recent_summaries=context.recent_summaries,
                style=style_from_state(),
                target_chars=int(target_chars),
                user_notes=user_notes,
                review=mode != "快速草稿",
                auto_repair=mode == "精修",
                extra_context=(context.prompt_sections() + "\n\n" + meta.get("outline_context", "")).strip(),
                reference_hashes=st.session_state.reference_hashes,
                historical_story_dna=[row for row in store.load_story_dna_history(project_name) if str(row.get("chapter_id")) != chapter_id],
                historical_voice_dna=[row for row in store.load_voice_dna_history(project_name) if str(row.get("chapter_id")) != chapter_id],
            )
            final_text = result.final_text
            overlap = reference_overlap(final_text, st.session_state.reference_hashes)
            previous_chapters = [
                row for row in store.all_chapter_texts(project_name)
                if row[0] != store.slugify(chapter_id)
            ]
            self_similarity = [
                item.__dict__ for item in near_duplicate_chapters(final_text, previous_chapters)
            ]
            write_author_chapter(store, project_name, chapter_id, final_text, allow_overwrite=allow_overwrite)
            save_chapter_plan(store, project_name, chapter_id, result.plan, final_text)
            st.session_state.last_result = result
            st.session_state.last_overlap = overlap
            st.session_state.last_self_similarity = self_similarity
            st.session_state.last_result_meta = {
                "project": project_name, "chapter_id": chapter_id,
                "text_sha256": hashlib.sha256((final_text.strip() + "\n").encode("utf-8")).hexdigest(),
            }
            st.session_state.last_extraction = None
            st.session_state.memory_candidate_json = None
            st.session_state.last_memory_commit = None
            st.success("章节已生成并保存到本地项目目录。")
        except Exception as exc:
            st.exception(exc)

    if st.session_state.pending_plan_json:
        if st.session_state.plan_new:
            st.session_state["plan_editor"] = st.session_state.pending_plan_json
            st.session_state.plan_new = False
        st.text_area(
            "场景计划（可直接编辑 JSON：改目标、阻力、选择、代价、知识边界后再写正文）",
            key="plan_editor",
            height=420,
        )

    result = st.session_state.last_result
    st.session_state.memory_displayed_text_sha256 = None
    if result:
        with st.expander("场景计划", expanded=False):
            st.json(result.plan.model_dump())
        shown_text = st.text_area("正文", value=result.final_text, height=720, disabled=True)
        st.session_state.memory_displayed_text_sha256 = hashlib.sha256((shown_text.strip() + "\n").encode("utf-8")).hexdigest()
        st.caption("此处只读显示已绑定版本。需要调整正文时，请通过修订与保存新版本流程处理，不能把未保存的显示编辑当作已接受稿。")
        if result.final_report:
            st.caption("下列文本诊断绑定当前显示正文；模型审校不等于作者接受。Story DNA/行为结构仍来自场景计划。")
            with st.expander("当前正文审校来源与范围", expanded=False):
                st.json({key: result.final_report[key] for key in (
                    "stage", "text_sha256", "plan_sha256", "review_status", "external_hooks", "author_acceptance")})
            with st.expander("初稿诊断记录（修订前）", expanded=False):
                st.json(result.initial_report)
        if st.session_state.last_self_similarity:
            top = st.session_state.last_self_similarity[:3]
            st.warning("跨章近似重复风险：" + "；".join(
                f"{row['chapter_id']}={row['score']:.1%}" for row in top
            ))
        if st.session_state.last_overlap > 0.01:
            st.warning(
                f"参考文本 18 字符片段哈希重合率 {st.session_state.last_overlap:.2%}，建议检查是否出现不必要的近似复用。"
            )
        if result.review:
            with st.expander("初稿编辑审校", expanded=False):
                st.json(result.review.model_dump())
        if result.review_after_repair:
            verdict = result.review_after_repair.verdict
            icon = "🟢" if verdict == "pass" else "🟠"
            with st.expander(f"{icon} 精修复审（verdict: {verdict}）", expanded=verdict != "pass"):
                st.json(result.review_after_repair.model_dump())
        with st.expander("本地 AI 味信号", expanded=False):
            st.json(result.ai_flavor)
        if result.quality_report:
            with st.expander("文本质量门", expanded=False):
                st.json(result.quality_report)
        if result.similarity_report:
            with st.expander("参考相似度保护门", expanded=False):
                st.json(result.similarity_report)
        if result.story_dna:
            with st.expander("Story DNA（场景计划派生，非正文事件抽取）", expanded=False):
                st.json(result.story_dna)
        if result.voice_dna_report:
            alerts = result.voice_dna_report.get("revised_alerts", result.voice_dna_report.get("alerts", []))
            if alerts:
                st.warning("人物口吻 DNA 漂移：" + "；".join(
                    f"{row['character']}={row['score']:.1%}" for row in alerts[:3]
                ))
            with st.expander("人物口吻 DNA（当前正文）", expanded=False):
                st.json(result.final_report["voice"] if result.final_report else result.voice_dna_report)
        if result.behavior_repetition_report:
            if result.behavior_repetition_report.get("should_avoid"):
                st.warning(f"人物行为模式重复：最高 {result.behavior_repetition_report.get('max_score',0):.1%}")
            with st.expander("人物行为模式重复", expanded=False):
                st.json(result.behavior_repetition_report)
        if result.story_dna_similarity_report:
            score = result.story_dna_similarity_report.get("max_score", 0)
            if result.story_dna_similarity_report.get("should_avoid"):
                st.warning(f"历史 Story DNA 套路/事件链近似：最高 {score:.1%}，已把去重约束注入本章生成与审校。")
            with st.expander("跨章节 Story DNA 重复检测", expanded=False):
                st.json(result.story_dna_similarity_report)
        if result.workflow_report:
            with st.expander("写作流程阶段检查", expanded=False):
                st.json(result.workflow_report)
        with st.expander("发布前综合质量快照", expanded=False):
            try:
                previous_for_eval = [row for row in store.all_chapter_texts(project_name) if row[0] != store.slugify(chapter_id)]
                st.json(build_release_quality_snapshot(
                    result.final_text,
                    reference_hashes=st.session_state.reference_hashes,
                    previous_chapters=previous_for_eval,
                ).to_dict())
            except (OSError, UnicodeError, ValueError) as exc:
                st.warning("综合质量快照未完成；请检查已有章节文件。其他审阅入口仍可使用：" + str(exc))

    render_memory_proposals(st, store, project_name, chapter_id, result,
        lambda: NovelEngine(make_provider(request_budget=RequestBudget(RequestBudgetLimits(
            max_requests=2, max_request_bytes=512 * 1024, max_total_request_bytes=1024 * 1024,
            max_reserved_output_tokens=16384)))))

    with st.expander("Story DNA 历史库", expanded=False):
        dna_history = store.load_story_dna_history(project_name)
        if dna_history:
            st.json(dna_history[-12:])
        else:
            st.info("还没有已持久化的 Story DNA。章节定稿并执行记忆回写后开始累积。")

    with st.expander("全书 Story DNA / 套路分析", expanded=False):
        dna_history = store.load_story_dna_history(project_name)
        analytics_history = store.load_chapter_analytics_history(project_name)
        if dna_history:
            st.markdown("#### 全书套路统计")
            st.json(trope_frequency(dna_history))
            st.markdown("#### Story DNA 聚类")
            st.json(cluster_story_dna(dna_history))
            coords = project_story_dna_2d(dna_history)
            if coords:
                st.markdown("#### Story DNA 2D 投影")
                try:
                    import pandas as pd
                    st.scatter_chart(pd.DataFrame(coords), x="x", y="y", color=None)
                except Exception:
                    st.json(coords)
        if analytics_history:
            drift = [item.to_dict() for item in detect_longform_drift(analytics_history)]
            st.markdown("#### 章节节奏 / 文风漂移")
            st.json(drift if drift else {"status":"暂无显著漂移"})
        if not dna_history and not analytics_history:
            st.info("还没有足够的长期数据。章节定稿并回写后会自动累积。")

    with st.expander("长篇一致性健康状态", expanded=False):
        health = store.load_longform_health(project_name)
        if health:
            if health.get("timeline_contradictions"):
                st.error(f"检测到 {len(health['timeline_contradictions'])} 个时间线矛盾候选。")
            if health.get("foreshadow_lifecycle",{}).get("overdue"):
                st.warning(f"过期伏笔候选：{len(health['foreshadow_lifecycle']['overdue'])}")
            if health.get("tension_density",{}).get("warnings"):
                for warning in health["tension_density"]["warnings"]:
                    st.warning(warning)
            st.markdown("#### 人物口吻 DNA / 漂移")
            st.json({
                "baseline": health.get("voice_baseline",{}),
                "drift": health.get("voice_drift",[]),
            })
            st.markdown("#### 人物行为模式重复")
            st.json(health.get("behavior_repetition",{}))
            st.markdown("#### 时间线矛盾")
            st.json(health.get("timeline_contradictions",[]))
            st.markdown("#### 伏笔生命周期")
            st.json(health.get("foreshadow_lifecycle",{}))
            st.markdown("#### 高潮 / 低谷密度")
            st.json(health.get("tension_density",{}))
        else:
            st.info("尚未生成长篇一致性健康状态；章节定稿并执行记忆回写后自动建立。")

    with st.expander("长期记忆状态（story_state）", expanded=False):
        state = store.load_story_state(project_name)
        if any(state.get(k) for k in ("facts", "timeline", "foreshadowing", "open_threads")):
            st.json(state)
        else:
            st.info("还没有已回写的长期记忆。生成章节后执行记忆抽取即可累积。")

with review_tab:
    st.subheader("独立文本审校")
    review_text = st.text_area("粘贴需要检查的正文", height=500)
    if st.button("本地质量门 + AI 味扫描"):
        if review_text.strip():
            q = analyze_prose_quality(review_text)
            sim = analyze_reference_similarity(review_text, reference_hashes=st.session_state.reference_hashes)
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("#### 文本质量门")
                st.json(q.to_dict())
            with c2:
                st.markdown("#### 参考相似度保护")
                st.json(sim.to_dict())
            with c3:
                st.markdown("#### AI 味启发式信号")
                st.json(detect_ai_flavor(review_text))
        else:
            st.warning("请先粘贴正文。")

st.divider()
st.caption("v0.2：长篇记忆内核（章节后处理回写 + Canon/Active/Recall 组装）。下一阶段：冻结多题材 A/B benchmark 与真实评测。")


with release_tab:
    render_release_workbench(store, project_name)
