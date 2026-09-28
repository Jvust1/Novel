from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field, field_validator

from .market_eval import MarketCorpus


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
    source_stage: str
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
    """
    corpus.validate_stage()
    return ReleasePack(
        profile=profile,
        title=title,
        one_line_hook=one_line_hook,
        short_blurb=short_blurb,
        long_blurb=long_blurb,
        tags=list(dict.fromkeys(tag.strip() for tag in tags if tag.strip())),
        chapter_count=len(corpus.chapters),
        corpus_sha256=corpus.fingerprint(),
        source_stage=corpus.stage,
        content_warnings=list(dict.fromkeys(item.strip() for item in content_warnings if item.strip())),
        manual_checks=list(dict.fromkeys(item.strip() for item in manual_checks if item.strip())),
        notes=[
            "Release Pack 只记录作者/编辑提供的发布元数据与语料摘要，不保存章节正文。",
            "平台曝光、推荐、签约与收益不能由此结构化包保证。",
        ],
    )


def save_release_pack(pack: ReleasePack, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(pack.model_dump(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def load_release_pack(path: str | Path) -> ReleasePack:
    return ReleasePack.model_validate_json(Path(path).read_text(encoding="utf-8"))
