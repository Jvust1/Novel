from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import StoryBible
from .storage import ProjectStore


@dataclass
class WritingContext:
    canon_block: str = ""
    active_block: str = ""
    recall_block: str = ""
    recent_summaries: list[dict[str, Any]] = field(default_factory=list)
    open_foreshadowing: list[dict[str, Any]] = field(default_factory=list)

    def prompt_sections(self) -> str:
        parts = [block for block in (self.canon_block, self.active_block, self.recall_block) if block]
        return "\n\n".join(parts)


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + "……"


class ContextAssembler:
    """Assemble bounded Canon / Active / Recall context for one chapter.

    Canon: locked facts and story-state facts (bible itself is passed to
    prompts separately, so only accumulated facts live here).
    Active: open foreshadowing plus recent chapter summaries.
    Recall: older summaries compressed to one line each, with a budget.
    """

    def __init__(
        self,
        store: ProjectStore,
        project: str,
        *,
        canon_char_budget: int = 1600,
        recall_char_budget: int = 1200,
        recall_summary_chars: int = 80,
    ):
        self.store = store
        self.project = project
        self.canon_char_budget = canon_char_budget
        self.recall_char_budget = recall_char_budget
        self.recall_summary_chars = recall_summary_chars

    def assemble(
        self,
        *,
        recent_limit: int = 4,
        max_open_foreshadowing: int = 8,
    ) -> WritingContext:
        state = self.store.load_story_state(self.project)
        summaries = self.store.all_chapter_summaries(self.project)

        context = WritingContext()

        facts = [str(f).strip() for f in state.get("facts", []) if str(f).strip()]
        threads = [str(t).strip() for t in state.get("open_threads", []) if str(t).strip()]
        canon_lines: list[str] = []
        if facts:
            canon_lines.append("已确立事实：\n" + "\n".join(f"- {f}" for f in facts))
        if threads:
            canon_lines.append("未回收线索：\n" + "\n".join(f"- {t}" for t in threads))
        canon_text = "\n\n".join(canon_lines)
        context.canon_block = (
            f"【Canon 长期记忆（硬约束，不得矛盾）】\n{_clip(canon_text, self.canon_char_budget)}"
            if canon_text
            else ""
        )

        recent = summaries[-recent_limit:] if recent_limit > 0 else []
        older = summaries[:-recent_limit] if recent_limit > 0 and len(summaries) > recent_limit else []
        context.recent_summaries = recent

        foreshadowing = [
            item for item in state.get("foreshadowing", []) if item.get("status") != "resolved"
        ][-max_open_foreshadowing:]
        context.open_foreshadowing = foreshadowing

        active_lines: list[str] = []
        if foreshadowing:
            active_lines.append("开放伏笔：\n" + "\n".join(
                f"- [{item.get('status', 'planted')}] {item.get('description', '')}" for item in foreshadowing
            ))
        if recent:
            active_lines.append("近章摘要：\n" + "\n".join(
                f"- {row.get('chapter_id', '')} {row.get('chapter_title', '')}：{row.get('summary', '')}"
                for row in recent
            ))
        context.active_block = "\n\n".join(active_lines)

        if older:
            recall_lines = [
                f"- {row.get('chapter_id', '')} {_clip(str(row.get('summary', '')), self.recall_summary_chars)}"
                for row in older
            ]
            recall_text = "更早章节（仅一行回顾，细节以已确立事实为准）：\n" + "\n".join(recall_lines)
            context.recall_block = f"【Recall 历史回顾】\n{_clip(recall_text, self.recall_char_budget)}"

        return context
