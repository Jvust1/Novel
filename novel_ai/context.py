from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import StoryBible
from .storage import ProjectStore
from .token_budget import TokenCounter
from .history_recall import select_history


@dataclass
class WritingContext:
    canon_block: str = ""
    active_block: str = ""
    recall_block: str = ""
    longform_block: str = ""
    recent_summaries: list[dict[str, Any]] = field(default_factory=list)
    open_foreshadowing: list[dict[str, Any]] = field(default_factory=list)
    recall_report: dict[str, Any] | None = None

    def prompt_sections(self) -> str:
        parts = [block for block in (self.canon_block, self.active_block, self.recall_block, self.longform_block) if block]
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
        token_counter: TokenCounter | None = None,
        canon_token_budget: int | None = None,
        recall_token_budget: int | None = None,
    ):
        self.store = store
        self.project = project
        self.canon_char_budget = canon_char_budget
        self.recall_char_budget = recall_char_budget
        self.recall_summary_chars = recall_summary_chars
        self.token_counter = token_counter
        self.canon_token_budget = canon_token_budget
        self.recall_token_budget = recall_token_budget

    def assemble(
        self,
        *,
        recent_limit: int = 4,
        max_open_foreshadowing: int = 8,
        recall_query: str = "",
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
            f"【Canon 长期记忆（硬约束，不得矛盾）】\n{(self.token_counter.clip(canon_text, self.canon_token_budget) if self.token_counter is not None and self.canon_token_budget is not None else _clip(canon_text, self.canon_char_budget))}"
            if canon_text
            else ""
        )

        recent = summaries[-recent_limit:] if recent_limit > 0 else []
        older = summaries[:-recent_limit] if recent_limit > 0 and len(summaries) > recent_limit else []
        if recall_query.strip():
            # Explicit experiment; keep the historical chronological default intact.
            older = summaries[:-recent_limit] if recent_limit > 0 else summaries
            older, context.recall_report = select_history(
                recall_query, older, summary_chars=max(0, self.recall_summary_chars)
            )
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

        health = self.store.load_longform_health(self.project)
        guard = str(health.get("guard_context", "") or "").strip()
        if guard:
            context.longform_block = "【Longform 长篇一致性】\n" + _clip(guard, 1400)

        if older:
            if context.recall_report is not None:
                # Bound the entire block, including labels; zero means disabled.
                header = "【Recall 多样化历史回顾（摘要线索，以 Canon 为准）】\n"
                lines = []
                included = []
                for row in older:
                    summary = row["recall_excerpt"]
                    line = f"- {str(row.get('chapter_id', ''))[:80]} {summary}"
                    candidate = header + "\n".join([*lines, line])
                    if len(candidate) > max(0, self.recall_char_budget):
                        continue
                    if self.recall_token_budget is not None and self.token_counter is not None:
                        if self.token_counter.count(candidate) > max(0, self.recall_token_budget):
                            continue
                    lines.append(line)
                    included.append(str(row.get("chapter_id", "")))
                context.recall_block = header + "\n".join(lines) if lines else ""
                context.recall_report["included_chapter_ids"] = included
                context.recall_report["prompt_chars"] = len(context.recall_block)
                return context
            recall_lines = [
                f"- {row.get('chapter_id', '')} {_clip(str(row.get('summary', '')), self.recall_summary_chars)}"
                for row in older
            ]
            recall_text = "更早章节（仅一行回顾，细节以已确立事实为准）：\n" + "\n".join(recall_lines)
            context.recall_block = f"【Recall 历史回顾】\n{(self.token_counter.clip(recall_text, self.recall_token_budget) if self.token_counter is not None and self.recall_token_budget is not None else _clip(recall_text, self.recall_char_budget))}"

        return context
