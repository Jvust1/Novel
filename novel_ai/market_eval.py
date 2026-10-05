from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, Field, field_validator

Stage = Literal["opening_3", "retention_20"]

MARKET_RUBRIC: tuple[tuple[str, str, str], ...] = (
    ("premise_clarity", "题材承诺清晰", "读者能否迅速知道主角、目标和主要看点"),
    ("opening_pull", "开篇拉力", "前三章是否形成具体问题、行动和继续阅读理由"),
    ("protagonist_agency", "主角主动性", "主角选择是否推动局面，而非只被动接收安排"),
    ("causal_escalation", "因果升级", "阻力和代价是否由先前选择自然升级"),
    ("payoff_cadence", "回报节奏", "悬念、行动与阶段性回报是否有合理间隔"),
    ("character_attachment", "人物牵引", "人物欲望、关系和变化能否持续牵引阅读"),
    ("continuity", "连续性", "时间、知识边界、世界规则和人物状态是否自洽"),
    ("chapter_hooks", "章末动力", "章节结束时是否有明确且不廉价的后续期待"),
    ("language_readability", "语言可读性", "叙述、对白和信息密度是否自然易读"),
    ("originality", "原创性", "是否存在可辨识的情节、事件链或表达复用风险"),
)

STAGE_SIZES: dict[Stage, int] = {"opening_3": 3, "retention_20": 20}


class MarketChapter(BaseModel):
    number: int
    title: str = ""
    text: str

    @field_validator("text")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("章节正文不能为空")
        return value


class MarketCorpus(BaseModel):
    """Owned or authorized chapter text supplied for offline human review."""

    project: str
    stage: Stage
    chapters: list[MarketChapter]
    audience: str = ""
    genre: str = ""
    review_note: str = ""

    @field_validator("chapters")
    @classmethod
    def consecutive_chapters(cls, chapters: list[MarketChapter]) -> list[MarketChapter]:
        if not chapters:
            raise ValueError("至少需要一章")
        numbers = [chapter.number for chapter in chapters]
        if numbers != list(range(1, len(numbers) + 1)):
            raise ValueError("章节编号必须从 1 连续递增")
        return chapters

    def validate_stage(self) -> "MarketCorpus":
        required = STAGE_SIZES[self.stage]
        if len(self.chapters) != required:
            raise ValueError(f"{self.stage} 需要恰好 {required} 章，当前为 {len(self.chapters)} 章")
        return self

    def fingerprint(self) -> str:
        canonical = json.dumps(
            {
                "schema": "market-corpus-v2",
                "project": self.project,
                "stage": self.stage,
                "audience": self.audience,
                "genre": self.genre,
                "review_note": self.review_note,
                "chapters": [(chapter.number, chapter.title, chapter.text) for chapter in self.chapters],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MarketScore(BaseModel):
    project: str
    stage: Stage
    corpus_sha256: str
    reviewer_id: str
    dimension: str
    score: int = Field(ge=1, le=5)
    note: str = ""

    @field_validator("reviewer_id")
    @classmethod
    def normalize_reviewer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reviewer_id 不能为空")
        return value


def market_scoring_csv(corpus: MarketCorpus) -> str:
    """Render the same blank, corpus-bound human scoring sheet in memory."""
    corpus.validate_stage()
    handle = io.StringIO(newline="")
    writer = csv.writer(handle)
    writer.writerow(
        ["project", "stage", "corpus_sha256", "reviewer_id", "dimension", "label", "score", "note", "anchor"]
    )
    for key, label, anchor in MARKET_RUBRIC:
        writer.writerow(
            [corpus.project, corpus.stage, corpus.fingerprint(), "", key, label, "", "", anchor]
        )
    return handle.getvalue()


def make_market_scoring_sheet(corpus: MarketCorpus, path: str | Path) -> Path:
    """Create a new blank sheet; never overwrite an existing review or input."""
    content = market_scoring_csv(corpus)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8-sig", newline="") as handle:
        handle.write(content)
    return target


def load_market_scores(path: str | Path, corpus: MarketCorpus) -> list[MarketScore]:
    """Load a file through the same strict parser used by the author workbench."""
    return parse_market_scores(Path(path).read_text(encoding="utf-8-sig"), corpus)


def parse_market_scores(content: str, corpus: MarketCorpus) -> list[MarketScore]:
    """Validate complete, corpus-bound scoring by one identified reviewer."""
    corpus.validate_stage()
    rows: list[MarketScore] = []
    handle = io.StringIO(content.lstrip("\ufeff"), newline="")
    reader = csv.DictReader(handle, strict=True)
    try:
        fields = reader.fieldnames
        if not fields:
            raise ValueError("评分表缺少 CSV 表头")
        if any(not field.strip() for field in fields):
            raise ValueError("评分表表头包含空列名")
        if len(fields) != len(set(fields)):
            raise ValueError("评分表表头包含重复列名")
        required = {"project", "stage", "corpus_sha256", "reviewer_id", "dimension", "score"}
        missing = required - set(fields)
        if missing:
            raise ValueError("评分表缺少必需列: " + ", ".join(sorted(missing)))
        for row in reader:
            line = reader.line_num
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"评分表第 {line} 行列数与表头不一致")
            score_text = row["score"].strip()
            if not score_text:
                raise ValueError(f"评分表未填完：第 {line} 行 score 为空，不得汇总")
            if score_text not in {"1", "2", "3", "4", "5"}:
                raise ValueError(f"评分表第 {line} 行 score 必须为 1 到 5 的整数")
            rows.append(
                MarketScore(
                    project=row["project"],
                    stage=row["stage"],
                    corpus_sha256=row["corpus_sha256"],
                    reviewer_id=row["reviewer_id"],
                    dimension=row["dimension"],
                    score=int(score_text),
                    note=row.get("note", ""),
                )
            )
    except csv.Error as exc:
        raise ValueError(f"评分表 CSV 格式错误（第 {reader.line_num} 行附近）: {exc}") from exc
    expected = {key for key, _, _ in MARKET_RUBRIC}
    actual = [row.dimension for row in rows]
    if len(rows) != len(expected) or set(actual) != expected:
        raise ValueError("评分维度缺失或重复")
    if any(
        row.project != corpus.project
        or row.stage != corpus.stage
        or row.corpus_sha256 != corpus.fingerprint()
        for row in rows
    ):
        raise ValueError("评分表与当前语料不匹配，不能汇总")
    reviewers = {row.reviewer_id.strip() for row in rows}
    if len(reviewers) != 1 or not next(iter(reviewers)):
        raise ValueError("必须填写同一位 reviewer_id")
    return rows


def aggregate_market_scores(rows: Sequence[MarketScore]) -> dict:
    """Summarize complete human ratings; no automatic publishability verdict."""
    expected = {key for key, _, _ in MARKET_RUBRIC}
    if len(rows) != len(expected) or {row.dimension for row in rows} != expected:
        raise ValueError("只能汇总完整且无重复维度的评分")
    identities = {(row.project, row.stage, row.corpus_sha256, row.reviewer_id) for row in rows}
    if len(identities) != 1:
        raise ValueError("不得混合不同语料、阶段或评审者")
    project, stage, digest, reviewer = identities.pop()
    if not reviewer.strip():
        raise ValueError("reviewer_id 不能为空")
    values = {row.dimension: row.score for row in rows}
    return {
        "project": project,
        "stage": stage,
        "corpus_sha256": digest,
        "reviewer_id": reviewer,
        "dimension_scores": values,
        "mean_score": round(sum(values.values()) / len(values), 3),
        "status": "human_review_recorded",
        "publishability_verdict": None,
        "note": "这是人工商业可读性记录；不等于平台推荐、签约或发布保证。",
    }


def load_market_corpus(path: str | Path) -> MarketCorpus:
    return MarketCorpus.model_validate_json(Path(path).read_text(encoding="utf-8")).validate_stage()
