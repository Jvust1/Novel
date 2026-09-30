from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field, field_validator, model_validator

from .market_eval import STAGE_SIZES, Stage, MarketCorpus


def _clean_items(items: Iterable[str], field_name: str) -> list[str]:
    """Validate list-like metadata without accidentally iterating strings."""
    if isinstance(items, (str, bytes)) or items is None:
        raise ValueError(f"{field_name} 必须是字符串列表")
    try:
        values = list(items)
    except TypeError as exc:
        raise ValueError(f"{field_name} 必须是字符串列表") from exc
    if any(not isinstance(item, str) for item in values):
        raise ValueError(f"{field_name} 必须是字符串列表")
    return list(dict.fromkeys(item.strip() for item in values if item.strip()))


class MarketProfile(BaseModel):
    """Explicit platform and audience assumptions for a release candidate."""

    platform: str = "番茄小说"
    genre: str
    audience: str
    tone: str = ""
    comparable_tags: list[str] = Field(default_factory=list)
    cadence: str = ""
    content_policy_notes: list[str] = Field(default_factory=list)

    @field_validator("genre", "audience")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("genre 和 audience 必须明确填写")
        return value.strip()

    @field_validator("comparable_tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        tags = [tag.strip() for tag in value if tag.strip()]
        if len(tags) != len(set(tags)):
            raise ValueError("comparable_tags 不得重复")
        return tags


class ReleasePack(BaseModel):
    """Human-reviewable release metadata bound to a supplied chapter corpus."""

    version: str = "0.1"
    profile: MarketProfile
    title: str
    one_line_hook: str
    short_blurb: str
    long_blurb: str = ""
    tags: list[str] = Field(default_factory=list)
    chapter_count: int
    corpus_sha256: str
    source_stage: Stage
    content_warnings: list[str] = Field(default_factory=list)
    manual_checks: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("title", "one_line_hook", "short_blurb")
    @classmethod
    def required_copy(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title、one_line_hook、short_blurb 不能留空")
        return value.strip()

    @field_validator("chapter_count")
    @classmethod
    def positive_chapters(cls, value: int) -> int:
        if value < 1:
            raise ValueError("chapter_count 必须至少为 1")
        return value

    @field_validator("corpus_sha256")
    @classmethod
    def valid_digest(cls, value: str) -> str:
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value.lower()):
            raise ValueError("corpus_sha256 必须是 64 位十六进制摘要")
        return value.lower()

    @model_validator(mode="after")
    def validate_provenance(self) -> "ReleasePack":
        expected = STAGE_SIZES[self.source_stage]
        if self.chapter_count != expected:
            raise ValueError(
                f"chapter_count 必须与 source_stage={self.source_stage} 匹配，当前应为 {expected}"
            )
        return self


def build_release_pack(
    corpus: MarketCorpus,
    profile: MarketProfile,
    *,
    title: str,
    one_line_hook: str,
    short_blurb: str,
    long_blurb: str = "",
    tags: Iterable[str] = (),
    content_warnings: Iterable[str] = (),
    manual_checks: Iterable[str] = (),
) -> ReleasePack:
    """Bind explicit release copy to the exact supplied corpus fingerprint.

    Copy is supplied by the author/editor. This function only validates and
    records provenance; it never calls a model or writes chapter text.
    The resulting pack is suitable for review before any platform submission.
    """
    corpus.validate_stage()
    return ReleasePack(
        profile=profile,
        title=title,
        one_line_hook=one_line_hook,
        short_blurb=short_blurb,
        long_blurb=long_blurb,
        tags=_clean_items(tags, "tags"),
        chapter_count=len(corpus.chapters),
        corpus_sha256=corpus.fingerprint(),
        source_stage=corpus.stage,
        content_warnings=_clean_items(content_warnings, "content_warnings"),
        manual_checks=_clean_items(manual_checks, "manual_checks"),
        notes=[
            "Release Pack 只记录作者/编辑提供的发布元数据与语料摘要，不保存章节正文。",
            "平台曝光、推荐、签约与收益不能由此结构化包保证。",
        ],
    )


def save_release_pack(pack: ReleasePack, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(pack.model_dump(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return target


def load_release_pack(path: str | Path) -> ReleasePack:
    return ReleasePack.model_validate_json(Path(path).read_text(encoding="utf-8"))
