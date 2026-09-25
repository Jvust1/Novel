from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path

import streamlit as st

from novel_ai.context import ContextAssembler
from novel_ai.engine import ChapterResult, NovelEngine
from novel_ai.memory import apply_extraction
from novel_ai.models import Character, ChapterPlan, MemoryExtraction, StoryBible, StyleFingerprint
from novel_ai.reading import extract_reference_text
from novel_ai.provider import OpenAICompatibleProvider, ProviderConfig
from novel_ai.storage import ProjectStore
from novel_ai.project_session import switch_project, plan_binding
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

store = ProjectStore(os.environ.get("NOVEL_DATA_DIR", "data"))

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


with st.sidebar:
    st.header("模型连接")
    base_url = st.text_input("Base URL", value="http://127.0.0.1:11434/v1", placeholder="本地 Ollama 或你授权的兼容端点")
    model = st.text_input("Model")
    api_key = st.text_input("API Key（只在当前会话使用）", type="password")
    st.caption("密钥不会由本应用写入项目文件。")
    st.divider()
    project_name = st.text_input("当前项目", value="MyNovel", key="project_name")
    st.caption("切换会隔离不同作品的草稿；未保存编辑仅在本次进程中保留。")
    target_chars = st.number_input("目标章节字数", min_value=800, max_value=15000, value=3500, step=200)


def make_provider() -> OpenAICompatibleProvider:
    if not base_url.strip() or not model.strip():
        raise ValueError("请先填写 Base URL 和 Model")
    return OpenAICompatibleProvider(
        ProviderConfig(base_url=base_url.strip(), model=model.strip(), api_key=api_key.strip())
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
        tone=tone,
        premise=premise,
        themes=[x.strip() for x in themes_text.splitlines() if x.strip()],
        world_rules=[x.strip() for x in rules_text.splitlines() if x.strip()],
        locked_facts=[x.strip() for x in locked_text.splitlines() if x.strip()],
        forbidden_moves=[x.strip() for x in forbidden_text.splitlines() if x.strip()],
    )


def seed_project_state() -> None:
    switch_project(st.session_state, store, project_name)


seed_project_state()


story_tab, char_tab, style_tab, write_tab, review_tab, manuscript_tab = st.tabs(
    ["📚 故事与大纲", "👥 人物", "🎛️ Style Lab", "✍️ 章节写作", "🔎 审校", "🗂️ 稿件与备份"]
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
        rules_text = st.text_area("世界规则（每行一个）", height=100, key="rules_text")
        locked_text = st.text_area("锁定事实（每行一个，不与世界规则混写）", height=100, key="locked_text")
        forbidden_text = st.text_area("明确禁止的剧情处理（每行一个）", height=100, key="forbidden_text")

    outline = st.text_area("总纲 / 卷纲 / 上层大纲", height=280, key="outline")
    if st.button("保存故事设定到本地", use_container_width=True):
        bible = current_bible()
        store.write_json(project_name, "memory/story_bible.json", bible.model_dump())
        store.write_json(project_name, "memory/outline.json", {"outline": outline})
        st.success("已原子保存到本地项目目录。")

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
            elif any(c["name"] == c_name.strip() for c in st.session_state.characters):
                st.warning("同名人物已存在；请编辑已有角色，不重复创建。")
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
    chapter_goal = st.text_area(
        "本章章纲 / 目标",
        placeholder="可以只有几句话。系统会先拆成场景，不会直接机械拉长。",
        height=180, key="chapter_goal",
    )
    user_notes = st.text_area("本章额外要求", placeholder="例如：本章不要揭晓真相；减少环境；最后停在门被推开……", height=100, key="chapter_notes")
    mode = st.radio("生成模式", ["快速草稿", "标准审校", "精修"], horizontal=True, index=1)
    confirm_plan = st.checkbox(
        "写正文前确认/编辑场景计划（推荐）",
        value=True,
        help="North Star 原则：AI 先给结构化建议，作者可编辑后再生成正文，不被全自动流水线绑架。",
    )

    if "pending_plan_json" not in st.session_state:
        st.session_state.pending_plan_json = ""
    if "pending_plan_meta" not in st.session_state:
        st.session_state.pending_plan_meta = {}
    if "plan_new" not in st.session_state:
        st.session_state.plan_new = False

    def _engine_and_inputs():
        engine = NovelEngine(make_provider())
        bible = current_bible()
        characters = [Character.model_validate(c) for c in st.session_state.characters]
        return engine, bible, characters

    current_binding = plan_binding(project_name, chapter_id, current_bible().model_dump(),
                                   st.session_state.characters, outline, chapter_goal)
    plan_matches = st.session_state.pending_plan_meta.get("binding") == current_binding
    if st.session_state.pending_plan_json and not plan_matches:
        st.warning("作品、章节、章纲或人物已变化。请重新生成并确认计划，旧计划保留供对照。")
    col1, col2, col3 = st.columns(3)
    with col1:
        make_plan = st.button("① 生成场景计划", use_container_width=True, key="btn_plan")
    with col2:
        write_draft = st.button(
            "② 按计划写正文",
            type="primary",
            use_container_width=True,
            disabled=not st.session_state.pending_plan_json or not plan_matches,
            key="btn_draft",
        )
    with col3:
        one_shot = st.button("一步生成", use_container_width=True, disabled=confirm_plan, help="跳过计划确认：计划→正文→审校一次完成", key="btn_oneshot")

    if make_plan:
        try:
            engine, bible, characters = _engine_and_inputs()
            context = ContextAssembler(store, project_name).assemble()
            plan = engine.plan(
                bible, outline, chapter_goal, characters, context.recent_summaries, context.prompt_sections()
            )
            st.session_state.pending_plan_json = plan.model_dump_json(indent=2)
            st.session_state.pending_plan_meta = {
                "recent": context.recent_summaries,
                "extra": context.prompt_sections(),
                "binding": current_binding,
            }
            st.session_state.plan_new = True
            st.rerun()
        except Exception as exc:
            st.exception(exc)

    if write_draft:
        try:
            if not plan_matches:
                raise ValueError("计划与当前作品上下文不匹配")
            engine, bible, characters = _engine_and_inputs()
            plan_json = st.session_state.get("plan_editor") or st.session_state.pending_plan_json
            plan = ChapterPlan.model_validate(json.loads(plan_json))
            meta = st.session_state.pending_plan_meta
            draft = engine.draft(
                bible,
                plan,
                characters,
                meta.get("recent", []),
                style_from_state(),
                int(target_chars),
                user_notes,
                meta.get("extra", ""),
            )
            review_result = None
            revised = None
            review_after_repair = None
            if mode != "快速草稿":
                review_result = engine.review(bible, plan, characters, draft)
                if mode == "精修" and review_result.verdict == "revise":
                    revised = engine.repair(draft, review_result, style_from_state())
                    review_after_repair = engine.review(bible, plan, characters, revised)
            st.session_state.last_result = ChapterResult(
                plan=plan,
                draft=draft,
                review=review_result,
                ai_flavor=detect_ai_flavor(draft),
                revised=revised,
                review_after_repair=review_after_repair,
            )
            final_text = st.session_state.last_result.final_text
            st.session_state.last_overlap = reference_overlap(final_text, st.session_state.reference_hashes)
            store.write_chapter(project_name, chapter_id, final_text)
            st.session_state.result_binding = (project_name, chapter_id, hashlib.sha256(final_text.encode()).hexdigest())
            st.session_state.memory_candidate = None
            st.success("章节已按确认的计划生成并保存到本地项目目录。")
        except Exception as exc:
            st.exception(exc)

    if one_shot:
        try:
            engine, bible, characters = _engine_and_inputs()
            context = ContextAssembler(store, project_name).assemble()
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
                extra_context=context.prompt_sections(),
            )
            st.session_state.last_result = result
            final_text = result.final_text
            st.session_state.last_overlap = reference_overlap(final_text, st.session_state.reference_hashes)
            store.write_chapter(project_name, chapter_id, final_text)
            st.session_state.result_binding = (project_name, chapter_id, hashlib.sha256(final_text.encode()).hexdigest())
            st.session_state.memory_candidate = None
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
    if result:
        with st.expander("场景计划", expanded=False):
            st.json(result.plan.model_dump())
        st.text_area("正文", value=result.final_text, height=720)
        if st.session_state.last_overlap > 0.01:
            st.warning(
                f"参考文本 18 字符片段哈希重合率 {st.session_state.last_overlap:.2%}，建议检查是否出现不必要的近似复用。"
            )
        if result.review:
            with st.expander("编辑审校", expanded=False):
                st.json(result.review.model_dump())
        if result.review_after_repair:
            verdict = result.review_after_repair.verdict
            icon = "🟢" if verdict == "pass" else "🟠"
            with st.expander(f"{icon} 精修复审（verdict: {verdict}）", expanded=verdict != "pass"):
                st.json(result.review_after_repair.model_dump())
        with st.expander("本地 AI 味信号", expanded=False):
            st.json(result.ai_flavor)

        st.divider()
        st.subheader("章节后处理 · 记忆抽取")
        st.caption("先抽取候选，作者确认后再回写；锁定人物仍受保护。")
        same_chapter = st.session_state.get("result_binding", ())[:2] == (project_name, chapter_id)
        if st.button("抽取记忆候选（先审阅，不自动回写）", use_container_width=True, disabled=not same_chapter):
            try:
                engine = NovelEngine(make_provider())
                extraction = engine.extract_memory(current_bible(),
                    [Character.model_validate(c) for c in st.session_state.characters], chapter_id, result.final_text)
                st.session_state.memory_candidate = {
                    "binding": st.session_state.result_binding,
                    "extraction": extraction.model_dump(),
                }
            except Exception as exc:
                st.exception(exc)
        candidate = st.session_state.get("memory_candidate")
        if candidate:
            st.json(candidate["extraction"])
            st.caption("逐项确认人物实际知道什么；候选抽取不是已确认事实。")
            if st.button("确认候选并回写本章记忆", disabled=not same_chapter):
                try:
                    if tuple(candidate["binding"]) != tuple(st.session_state.result_binding):
                        raise ValueError("正文已变化，请重新抽取")
                    extraction = MemoryExtraction.model_validate(candidate["extraction"])
                    new_characters, new_state = apply_extraction(
                        [Character.model_validate(c) for c in st.session_state.characters],
                        store.load_story_state(project_name), extraction)
                    # Recovery snapshot precedes the multi-file memory write.
                    before = store.export_project(project_name)
                    backup = store.project_dir(project_name) / "exports" / ("before-memory-" + hashlib.sha256(before).hexdigest()[:16] + ".zip")
                    if not backup.exists():
                        backup.write_bytes(before)
                    store.save_story_state(project_name, new_state)
                    store.save_extraction(project_name, extraction.model_dump())
                    store.write_json(project_name, "memory/characters.json", [c.model_dump() for c in new_characters])
                    st.session_state.characters = [c.model_dump() for c in new_characters]
                    st.session_state.last_extraction = extraction.model_dump()
                    st.session_state.memory_candidate = None
                    st.success("已回写；人物卡也已持久保存。回写前完整快照保留在本项目 exports 目录。")
                except Exception as exc:
                    st.exception(exc)

        if st.session_state.last_extraction:
            with st.expander("本次抽取结果", expanded=False):
                st.json(st.session_state.last_extraction)

    with st.expander("长期记忆状态（story_state）", expanded=False):
        state = store.load_story_state(project_name)
        if any(state.get(k) for k in ("facts", "timeline", "foreshadowing", "open_threads")):
            st.json(state)
        else:
            st.info("还没有已回写的长期记忆。生成章节后执行记忆抽取即可累积。")

with review_tab:
    st.subheader("独立文本审校")
    review_text = st.text_area("粘贴需要检查的正文", height=500)
    if st.button("只做本地 AI 味扫描"):
        if review_text.strip():
            st.json(detect_ai_flavor(review_text))
        else:
            st.warning("请先粘贴正文。")

with manuscript_tab:
    st.subheader("稿件编辑、历史版本与项目备份")
    st.caption("不连接模型也可整理和保存稿件。编辑后点击保存；关闭前导出项目备份。")
    project_dir = store.project_dir(project_name)
    chapters = sorted(p.stem for p in (project_dir / "chapters").glob("*.md"))
    chosen = st.selectbox("已有章节", ["新章节"] + chapters, key="manuscript_choice")
    manual_id = st.text_input("保存为章节编号", value="001", key="manual_chapter")
    def load_chosen_chapter():
        st.session_state.manual_manuscript = (project_dir / "chapters" / (chosen + ".md")).read_text(encoding="utf-8")
        st.session_state.manual_chapter = chosen
    st.button("加载选中章节", disabled=chosen == "新章节", on_click=load_chosen_chapter)
    text = st.text_area("手工编辑正文", key="manual_manuscript", height=500)
    if st.button("保存稿件并保留上一版", type="primary"):
        if not text.strip():
            st.warning("空稿件不覆盖已有正文。")
        else:
            path = store.write_chapter(project_name, manual_id, text)
            st.success("已保存：" + path.name + "；旧正文按内容哈希保留在 chapters/history。")
    st.download_button("导出当前编辑稿（Markdown）", text, file_name=store.slugify(manual_id)+".md", mime="text/markdown")
    with st.expander("历史正文（不会覆盖当前稿）"):
        history = sorted((project_dir / "chapters" / "history" / store.slugify(manual_id)).glob("*.md"))
        if history:
            revision = st.selectbox("历史版本哈希", [x.name for x in history])
            previous_text = (project_dir / "chapters" / "history" / store.slugify(manual_id) / revision).read_text(encoding="utf-8")
            st.code(previous_text, language=None)
            st.download_button("导出选中历史稿", previous_text, file_name="history-"+revision)
        else:
            st.info("尚无历史稿；首次改写已有章节时自动保留。")
    if st.button("生成完整项目备份"):
        st.session_state["backup_bytes"] = store.export_project(project_name)
        st.session_state["backup_project"] = project_name
    if st.session_state.get("backup_project") == project_name and st.session_state.get("backup_bytes"):
        st.download_button("下载项目 ZIP 备份", st.session_state["backup_bytes"],
                           file_name=store.slugify(project_name)+"-backup.zip", mime="application/zip")
    imported = st.file_uploader("恢复 ZIP 到一个新项目（不覆盖任何旧项目）", type=["zip"])
    restore_name = st.text_input("新恢复项目名", value=project_name+"-恢复")
    if st.button("校验并创建恢复项目", disabled=imported is None):
        try:
            path = store.restore_project(imported.getvalue(), restore_name)
            st.success("已恢复到新项目："+path.name+"。在侧栏切换到这个项目即可查看。")
        except Exception as exc:
            st.error(str(exc))
    st.caption("数据目录：" + str(project_dir))

st.divider()
st.caption("桌面交付候选版：本地写作与版本保护。模型生成需要你明确配置并触发；写作质量与人物知识归属需作者复核。")
