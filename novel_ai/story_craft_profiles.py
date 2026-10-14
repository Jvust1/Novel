"""Small, explicit genre payoff lenses, not genre inference or quality scoring.

Only library-owned text can enter system prompts. Unknown/ambiguous labels
fall back to the author's original genre/tone already present in the user data.
"""
from __future__ import annotations

import re
from typing import Literal


GenreStage = Literal["plan", "draft", "review"]

# Each row is: reader payoff, scene execution, editorial question.
PROFILES: dict[str, tuple[str, str, str]] = {
    "都市/日常": (
        "让生活目标、体面、相处方式或归属感有可感的小变化；一顿饭、一次告别也能完整兑现。",
        "从人物各自关心的具体麻烦选细节；幽默来自处境与应答，温暖来自相处方式，不靠旁白宣布治愈。",
        "读者能否从做事或说话的变化感到关系推进，而不是只听旁白说更亲近？没有危机不扣分。",
    ),
    "言情": (
        "让接近、信任、界限或承诺发生双向选择；吸引来自对这个人的具体认识，不以强迫或拖延误会代替发展。",
        "按既有关系阶段写主动、试探、拒绝与回应；当事人在意的细节有偏向，别把爱情压缩成脸红心跳的轮换。",
        "关系是否真的前进或重新划界？能否理解双方的自主选择？直白表达也可有效，不强添第三者。",
    ),
    "悬疑": (
        "让调查验证或排除一项已给解释，或明确缩小问题；未破案也应交付可核验的认识进展。",
        "让观察、推断、求证各有落点；人物根据对方回应调整问法，保留证据与猜测的区别及公平的信息顺序。",
        "本章增加的是证据支持的认识，还是只多了谜语？不得靠扣住视角人物已知或新增证据制造反转。",
    ),
    "玄幻/仙侠": (
        "将成长、胜负或守护兑现为已有能力与规则下的选择；收获要具体，同伴有贡献，成本按计划延续。",
        "关键交手写清目标、位置、可用手段与应变，让读者看懂怎样赢或怎样败，而不堆威压和围观惊叹。",
        "成就是否靠可理解的行动获得？不要把词句更壮阔当作升级战力，更不能消除既定代价。",
    ),
    "奇幻": (
        "让陌生世界的规则影响一个可理解的人物需要；惊奇来自规则被实际使用，而不只是新增专名。",
        "通过交易、礼节、旅行或代价展现已给世界；解释放在人物必须作决定的位置，留出感受陌生的余地。",
        "世界是否真的改变了人物的选项？专名说明有没有挤掉人物行动？不能靠临时魔法补逻辑。",
    ),
    "科幻": (
        "将技术约束转成人必须承担的取舍；发现、合作、资源分配或观念改变都能构成回报。",
        "保持测量、假设和未知分层；用人物职责与眼前尺度呈现影响，让解释参与决定，而不是轮流讲课。",
        "技术条件有没有进入选择和后果？是否守住数量、延迟与能力边界？乐观或抒情不等于不严谨。",
    ),
    "历史": (
        "让制度、身份、人情和承诺共同约束行动；回报可以是办成一件事，也可以是看清有限选择的代价。",
        "让称谓、礼数和说话分寸参与交涉；把时代限制落实到可做与不可做，不用伪文言替代清楚的动作。",
        "人物是否在已设时代条件内行动？谁承担了决定的后果？没有来源不能补史实或预知未来。",
    ),
    "武侠": (
        "让胜负与守诺、情义、名声或抉择相连；能赢与该不该出手可以是不同问题，不必一概两难。",
        "交手保持方位、先后手和伤势可追踪；对坐与行旅可舒展，让人物怎样对待承诺显出声气。",
        "读者是否看懂关键判断及其与江湖关系的联系？不能用留白遮掉胜负因果或凭空添招式。",
    ),
    "恐怖": (
        "依已给规则让人物对安全的理解发生变化；求证、暂时逃脱或明确代价也能兑现，不只续订惊吓。",
        "从已成立的正常状态写偏差与人物应对，让否认、求助、确认有不同节奏；不连堆阴森形容词。",
        "不安是否来自可定位的异常和后果？不以新增异象、角色降智或不获准的真相解释强行吓人。",
    ),
}

ALIASES = {
    "都市": "都市/日常", "日常": "都市/日常", "都市日常": "都市/日常",
    "言情": "言情", "关系向": "言情",
    "悬疑": "悬疑", "推理": "悬疑", "悬疑推理": "悬疑",
    "玄幻": "玄幻/仙侠", "仙侠": "玄幻/仙侠",
    "奇幻": "奇幻", "科幻": "科幻",
    "历史": "历史", "架空历史": "历史",
    "武侠": "武侠", "恐怖": "恐怖", "惊悚": "恐怖",
}


def resolve_craft_genres(genre: str) -> tuple[str, ...]:
    """Resolve at most two explicit labels in author order; never scan prose.

    Unknown tokens or more than two distinct families make the configuration
    ambiguous: no automatic lens is added. Original genre text is not altered.
    """
    if not isinstance(genre, str):
        raise TypeError("genre must be text")
    tokens = re.split(r"[+/＋／、,，;；|｜]", genre.strip())
    selected: list[str] = []
    for token in tokens:
        canonical = ALIASES.get(token.strip())
        if canonical is None:
            return ()
        if canonical not in selected:
            selected.append(canonical)
    return tuple(selected) if len(selected) <= 2 else ()


def genre_craft_rules(genre: str, stage: GenreStage) -> str:
    """Return only static, stage-specific suggestions; never an output schema."""
    if stage not in ("plan", "draft", "review"):
        raise ValueError("unsupported story craft stage")
    selected = resolve_craft_genres(genre)
    if not selected:
        return ""
    index = ("plan", "draft", "review").index(stage)
    lines = [
        "【类型阅读回报：候选镜头，不是套路配额】",
        "本书已定语气、作者要求和本章功能优先；辅类型只补充相关场面，不改变主声音。",
    ]
    for position, name in enumerate(selected):
        role = "主类型" if position == 0 else "辅类型"
        lines.append(f"{role} {name}：{PROFILES[name][index]}")
    return "\n\n" + "\n".join(lines)
