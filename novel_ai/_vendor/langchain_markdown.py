"""Lossless outline sections adapted from LangChain's Markdown header splitter.

Copyright (c) LangChain, Inc. MIT License; see third_party/langchain/LICENSE.
Source: langchain-ai/langchain @ a9780cd3dd73135d21d7130b08711685f2700d51
libs/text-splitters/langchain_text_splitters/markdown.py
MarkdownHeaderTextSplitter.split_text

The header-stack pop/push and fenced-code state machine are source adaptations.
Novel keeps each heading as a section, preserves note whitespace, records parent
indices/line numbers, and rejects unclosed fences. It does not use LangChain's
lossy content normalization, metadata aggregation, Document, or runtime package.
Fence closing is tightened to the opening marker's character and minimum length.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class MarkdownSection:
    level: int
    title: str
    line: int
    parent_index: int | None
    body: str = ""


def _trim_outer_blank_lines(lines: list[str]) -> str:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return "\n".join(lines[start:end])


def split_header_sections(text: str) -> list[MarkdownSection]:
    """Keep every ATX heading and its notes, with fenced headings left as notes.

    This is a bounded outline grammar, not a complete Markdown renderer. Only
    ATX headings and backtick/tilde fences indented by up to three spaces have
    structure. Unsupported Markdown is preserved as body text. Blank preamble is
    allowed; nonblank preamble raises rather than being silently discarded.
    Line endings are normalized to LF; interior whitespace is otherwise kept.
    """
    if not isinstance(text, str):
        raise ValueError("Markdown 大纲必须是文本")

    sections: list[MarkdownSection] = []
    # Adapted from LangChain: pop headings of equal or deeper level, then push.
    header_stack: list[tuple[int, int]] = []
    current_content: list[str] = []
    in_code_block = False
    opening_fence = ""
    opening_line = 0

    # str.splitlines also consumes Unicode separators/control characters inside
    # author notes; normalize only actual CR/LF line endings before splitting.
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line_number, line in enumerate(lines, start=1):
        stripped_line = line.lstrip(" ")
        structural = len(line) - len(stripped_line) <= 3

        # Adapted from LangChain's explicit fence state, retaining original text.
        # Unlike its RAG splitter, a shorter fence or ```word cannot close one.
        if in_code_block:
            closing = re.fullmatch(r"(`{3,}|~{3,})[ \t]*", stripped_line)
            if (
                structural
                and closing
                and closing[1][0] == opening_fence[0]
                and len(closing[1]) >= len(opening_fence)
            ):
                in_code_block = False
                opening_fence = ""
            current_content.append(line)
            continue

        fence = re.match(r"^(`{3,}|~{3,})(.*)$", stripped_line) if structural else None
        if fence and not (fence[1][0] == "`" and "`" in fence[2]):
            if not sections:
                raise ValueError(f"第 {line_number} 行：全书标题前存在正文，不能丢弃")
            in_code_block = True
            opening_fence = fence[1]
            opening_line = line_number
            current_content.append(line)
            continue

        header = re.fullmatch(r"(#+)(?:[ \t]+(.*))?", stripped_line) if structural else None
        if header:
            if sections:
                sections[-1].body = _trim_outer_blank_lines(current_content)
            current_content = []
            current_header_level = len(header[1])
            # Optional closing hashes are Markdown syntax, not title content.
            header_text = re.sub(r"(?:^|[ \t]+)#+[ \t]*$", "", header[2] or "").strip()
            while header_stack and header_stack[-1][0] >= current_header_level:
                header_stack.pop()
            parent_index = header_stack[-1][1] if header_stack else None
            sections.append(
                MarkdownSection(current_header_level, header_text, line_number, parent_index)
            )
            header_stack.append((current_header_level, len(sections) - 1))
        elif not sections:
            if line.strip():
                raise ValueError(f"第 {line_number} 行：全书标题前存在正文，不能丢弃")
        else:
            current_content.append(line)

    if in_code_block:
        raise ValueError(f"第 {opening_line} 行：代码围栏未闭合，不能确定后续大纲层级")
    if sections:
        sections[-1].body = _trim_outer_blank_lines(current_content)
    return sections
