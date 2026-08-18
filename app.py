from __future__ import annotations

import streamlit as st

from novel_ai.engine import NovelEngine
from novel_ai.models import Character, StoryBible, StyleFingerprint
from novel_ai.provider import OpenAICompatibleProvider, ProviderConfig
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


with st.sidebar:
    st.header("模型连接")
    base_url = st.text_input("Base URL", placeholder="例如本地或云端 OpenAI-compatible endpoint")
    model = st.text_input("Model")
    api_key = st.text_input("API Key（只在当前会话使用）", type="password")
    st.caption("密钥不会由本应用写入项目文件。")
    st.divider()
    project_name = st.text_input("当前项目", value="MyNovel")
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
        locked_facts=[x.strip() for x in rules_text.splitlines() if x.strip()],
        forbidden_moves=[x.strip() for x in forbidden_text.splitlines() if x.strip()],
    )


story_tab, char_tab, style_tab, write_tab, review_tab = st.tabs(
    ["📚 故事与大纲", "👥 人物", "🎛️ Style Lab", "✍️ 章节写作", "🔎 审校"]
)

with story_tab:
    col1, col2 = st.columns(2)
    with col1:
        title = st.text_input("书名", value=project_name)
        genre = st.text_input("题材", placeholder="都市 / 玄幻 / 悬疑 / 言情 / 科幻……")
        tone = st.text_input("基调", placeholder="克制、冷幽默、压迫、热血……")
        premise = st.text_area("核心设定 / Premise", height=130)
    with col2:
        themes_text = st.text_area("主题（每行一个）", height=100)
        rules_text = st.text_area("世界规则 / 锁定事实（每行一个）", height=130)
        forbidden_text = st.text_area("明确禁止的剧情处理（每行一个）", height=100)

    outline = st.text_area("总纲 / 卷纲 / 上层大纲", height=280)
    if st.button("保存故事设定到本地", use_container_width=True):
        bible = current_bible()
        store.write_json(project_name, "memory/story_bible.json", bible.model_dump())
        store.write_json(project_name, "memory/outline.json", {"outline": outline})
        st.success("已保存到本地 data/projects 目录。")

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

    uploaded = st.file_uploader("上传参考文本（v0.1 支持 TXT / MD）", type=["txt", "md"])
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
            text = uploaded.getvalue().decode("utf-8", errors="ignore")
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
    chapter_id = st.text_input("章节编号 / 名称", value="001")
    chapter_goal = st.text_area(
        "本章章纲 / 目标",
        placeholder="可以只有几句话。系统会先拆成场景，不会直接机械拉长。",
        height=180,
    )
    user_notes = st.text_area("本章额外要求", placeholder="例如：本章不要揭晓真相；减少环境；最后停在门被推开……", height=100)
    mode = st.radio("生成模式", ["快速草稿", "标准审校", "精修"], horizontal=True, index=1)

    if st.button("生成本章", type="primary", use_container_width=True):
        try:
            engine = NovelEngine(make_provider())
            bible = current_bible()
            characters = [Character.model_validate(c) for c in st.session_state.characters]
            recent = store.recent_chapter_summaries(project_name)
            result = engine.run(
                bible=bible,
                outline=outline,
                chapter_goal=chapter_goal,
                characters=characters,
                recent_summaries=recent,
                style=style_from_state(),
                target_chars=int(target_chars),
                user_notes=user_notes,
                review=mode != "快速草稿",
                auto_repair=mode == "精修",
            )
            st.session_state.last_result = result
            final_text = result.revised or result.draft
            st.session_state.last_overlap = reference_overlap(final_text, st.session_state.reference_hashes)
            store.write_chapter(project_name, chapter_id, final_text)
            st.success("章节已生成并保存到本地项目目录。")
        except Exception as exc:
            st.exception(exc)

    result = st.session_state.last_result
    if result:
        with st.expander("场景计划", expanded=False):
            st.json(result.plan.model_dump())
        st.text_area("正文", value=result.revised or result.draft, height=720)
        if st.session_state.last_overlap > 0.01:
            st.warning(
                f"参考文本 18 字符片段哈希重合率 {st.session_state.last_overlap:.2%}，建议检查是否出现不必要的近似复用。"
            )
        if result.review:
            with st.expander("编辑审校", expanded=False):
                st.json(result.review.model_dump())
        with st.expander("本地 AI 味信号", expanded=False):
            st.json(result.ai_flavor)

with review_tab:
    st.subheader("独立文本审校")
    review_text = st.text_area("粘贴需要检查的正文", height=500)
    if st.button("只做本地 AI 味扫描"):
        if review_text.strip():
            st.json(detect_ai_flavor(review_text))
        else:
            st.warning("请先粘贴正文。")

st.divider()
st.caption("v0.1：先验证长篇写作内核。下一阶段：RAG、人物关系图、伏笔面板、DOCX/PDF 导入、章节状态自动回写与桌面封装。")
