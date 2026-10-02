"""Import an author's explicit five-level Markdown outline without invention."""

from __future__ import annotations

from ._vendor.langchain_markdown import split_header_sections
from .outline import HierarchicalOutline, OutlineNode, _stable_id, validate_outline


_LEVELS = ("series", "volume", "arc", "chapter", "scene")


def parse_markdown_outline(
    text: str, *, title: str, premise: str = ""
) -> HierarchicalOutline:
    """Parse # series / ## volume / ### arc / #### chapter / ##### scene.

    Body text is author-supplied planning notes, never inferred conflict/outcome
    fields. A single root and continuous parent levels are required. Position
    IDs distinguish equal-title siblings and are deterministic for equal input;
    reordering/inserting nodes may change IDs. Parsing never writes or calls a
    provider. ``title`` labels the project; the root keeps its Markdown title.
    """
    if not isinstance(title, str) or not isinstance(premise, str):
        raise ValueError("title 和 premise 必须是文本")
    sections = split_header_sections(text)
    if not sections:
        raise ValueError("大纲需要一个 # 全书标题")

    nodes: list[OutlineNode] = []
    positions: list[str] = []
    sibling_counts: dict[int | None, int] = {}
    root: OutlineNode | None = None
    for section in sections:
        prefix = f"第 {section.line} 行："
        if not 1 <= section.level <= len(_LEVELS):
            raise ValueError(prefix + "大纲仅支持 # 到 ##### 五级标题")
        if not section.title:
            raise ValueError(prefix + "大纲标题不能为空")
        if section.level == 1:
            if root is not None:
                raise ValueError(prefix + "大纲只能有一个 # 全书根节点")
        elif section.parent_index is None:
            raise ValueError(prefix + "大纲必须从 # 全书根节点开始，层级不能跳过")
        elif sections[section.parent_index].level != section.level - 1:
            raise ValueError(prefix + "大纲层级不连续，不能跳过卷、情节线或章")

        count = sibling_counts.get(section.parent_index, 0) + 1
        sibling_counts[section.parent_index] = count
        position = (
            f"{positions[section.parent_index]}.{count}"
            if section.parent_index is not None
            else str(count)
        )
        level = _LEVELS[section.level - 1]
        node = OutlineNode(
            id=_stable_id(level, f"md-{position}", section.title),
            level=level,
            title=section.title,
            promise=section.body,
            metadata={
                "source": "markdown_outline",
                "parser": "langchain-markdown-adapted-v1",
                "heading_level": section.level,
                "source_line": section.line,
                "outline_position": position,
                "author_notes": section.body,
            },
        )
        nodes.append(node)
        positions.append(position)
        if section.parent_index is None:
            root = node
        else:
            nodes[section.parent_index].children.append(node)

    assert root is not None  # A non-root first heading has already failed closed.
    return validate_outline(
        HierarchicalOutline(
            title=title.strip() or root.title,
            premise=premise,
            root=root,
            notes=[
                "Markdown 正文只记录为作者大纲笔记，不推断人物、冲突、结果或生成正文。",
                "相同输入生成相同位置 ID；插入、重排或重命名节点可能改变 ID，需重新确认章节绑定。",
            ],
        )
    )
