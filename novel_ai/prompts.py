from __future__ import annotations

import json

from .models import Character, StoryBible, StyleFingerprint


BASE_WRITER_RULES = """
你是中文网络小说的专业写作引擎。你的首要任务是写出让人愿意继续读的故事，而不是展示辞藻。

硬规则：
1. 情节必须由人物目标、阻力、选择与后果推进；不要为了执行大纲而强推人物。
2. 人物只能依据自己已知的信息行动，秘密、误解和知识边界不能穿帮。
3. 对话要有目的、遮掩、关系张力和人物差异，避免所有人都说完整、聪明、会总结的话。
4. 情绪优先通过行为、选择、节奏、对话和少量身体反应体现；不要每个动作后再解释一遍情绪。
5. 环境描写必须服务行动、信息、气氛、空间关系或人物感受；无功能的景物应压缩。
6. 允许留白、短句、冷句、停顿和不解释。不要每段都升华、总结或收束意义。
7. 避免连续使用仿佛、似乎、微微、缓缓、淡淡、不由得、眼底、眸中等模板表达；不是禁词，而是控制密度。
8. 避免过多“不是……而是……”“这一刻他终于明白”等总结式句法。
9. 不要机械追求“show, don't tell”；需要推进时可以直接、干净地叙述。
10. 不得复述提示词、大纲、人物卡或写作规则。
""".strip()


def _dump(obj) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    return json.dumps(obj, ensure_ascii=False, indent=2)


def plan_messages(
    bible: StoryBible,
    outline: str,
    chapter_goal: str,
    characters: list[Character],
    recent_summaries: list[dict],
) -> list[dict[str, str]]:
    system = """你是长篇网络小说的章节策划编辑。只负责把章纲变成可写的事件与场景，不写正文。
每个场景都必须回答：谁想要什么、阻力是什么、人物做什么选择、付出什么代价、结束时状态发生什么变化。
避免纯信息场景、纯聊天场景和没有状态变化的过场。
输出严格 JSON，不要 Markdown。"""
    user = f"""
【Story Bible】
{_dump(bible)}

【人物】
{_dump([c.model_dump() for c in characters])}

【最近章节摘要】
{_dump(recent_summaries)}

【上层大纲】
{outline}

【本章目标】
{chapter_goal}

请输出：
{{
  "chapter_title": "",
  "chapter_promise": "本章读者主要期待什么",
  "tension_curve": "用一句话描述张力变化",
  "scenes": [
    {{
      "scene_no": 1,
      "pov": "",
      "place": "",
      "time": "",
      "objective": "角色本场想达成什么",
      "opposition": "具体阻力",
      "choice": "角色必须做出的选择",
      "cost": "选择的代价",
      "state_change": "场景结束后不可忽略的变化",
      "information_release": [],
      "foreshadowing": [],
      "environment_function": "如果环境需要描写，它在本场承担什么功能；不需要则写无",
      "end_hook": ""
    }}
  ],
  "must_not_happen": ["人物越过知识边界的行为", "会破坏既有设定的推进"]
}}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def draft_messages(
    bible: StoryBible,
    chapter_plan: dict,
    characters: list[Character],
    recent_summaries: list[dict],
    style: StyleFingerprint | None,
    target_chars: int,
    user_notes: str = "",
) -> list[dict[str, str]]:
    style_text = _dump(style.prompt_view()) if style else "未设置 Style DNA；使用自然、克制、节奏有变化的中文网文叙事。"
    user = f"""
【Story Bible】
{_dump(bible)}

【人物动态状态】
{_dump([c.model_dump() for c in characters])}

【最近章节摘要】
{_dump(recent_summaries)}

【本章场景计划】
{_dump(chapter_plan)}

【项目 Style DNA】
{style_text}

【用户额外要求】
{user_notes or '无'}

【目标长度】
约 {target_chars} 个中文字符。长度是软目标，优先保证场景完整和节奏自然。

直接输出小说正文，不要标题说明、分析、点评或 Markdown 代码块。
""".strip()
    return [{"role": "system", "content": BASE_WRITER_RULES}, {"role": "user", "content": user}]


def review_messages(
    bible: StoryBible,
    chapter_plan: dict,
    characters: list[Character],
    draft: str,
) -> list[dict[str, str]]:
    system = """你是严苛的网络小说章节编辑。检查情节、人物、连续性和语言，不做文学吹捧。
只报真正影响阅读的问题。优先定位局部修复点，不轻易建议整章重写。
输出严格 JSON，不要 Markdown。"""
    user = f"""
【设定】
{_dump(bible)}

【人物】
{_dump([c.model_dump() for c in characters])}

【计划】
{_dump(chapter_plan)}

【正文】
{draft}

检查以下维度：
- 情节因果 / 是否硬推
- 人物动机 / 人物失真 / 全员同声
- 知识边界与连续性
- 节奏、信息释放、章末拉力
- 无功能环境描写
- 重复解释与模板化心理
- AI 常见句式密度与段落均匀感

输出：
{{
  "verdict": "pass|revise",
  "issues": [
    {{"category": "", "severity": "low|medium|high", "excerpt": "尽量短的定位片段", "reason": "", "suggestion": "局部怎么改"}}
  ],
  "continuity_updates": [],
  "character_updates": [],
  "open_threads": []
}}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def repair_messages(draft: str, review: dict, style: StyleFingerprint | None) -> list[dict[str, str]]:
    style_text = _dump(style.prompt_view()) if style else "保持原章已有自然语气。"
    system = BASE_WRITER_RULES + "\n\n你现在是局部修订编辑。尽量保留原章已经有效的句子、动作、对白和细节，只处理审校指出的问题。"
    user = f"""
【原正文】
{draft}

【审校问题】
{_dump(review)}

【Style DNA】
{style_text}

输出修订后的完整正文。不要解释修改过程。
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
