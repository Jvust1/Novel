from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from .models import StyleFingerprint
from .reading import extract_reference_text
from .story_dna import StoryDNA, build_story_dna
from .style_engine import analyze_style, blend_styles, build_reference_signature


_CHAPTER_RE = re.compile(r"(?m)^\s*第[0-9一二三四五六七八九十百千万零〇两]+[章节卷回]\s*[^\n]*")


class ReferenceSourceProfile(BaseModel):
    source_id: str
    filename: str
    weight: float = 1.0
    char_count: int = 0
    paragraph_count: int = 0
    chapter_marker_count: int = 0
    style: StyleFingerprint
    signature_hashes: list[str] = Field(default_factory=list)
    token_stats: dict[str, float | int] = Field(default_factory=dict)


class ReferencePack(BaseModel):
    name: str = "reference-pack"
    source_count: int
    sources: list[ReferenceSourceProfile]
    blended_style: StyleFingerprint
    story_dna: StoryDNA | None = None
    notes: list[str] = Field(default_factory=list)


def _jieba_stats(text: str) -> dict[str, float | int]:
    """Optional Chinese token statistics; never required for the core pack."""
    try:
        import jieba
    except ImportError:
        return {"backend": 0, "token_count": 0, "unique_token_ratio": 0.0}

    tokens = [tok.strip() for tok in jieba.lcut(text) if tok.strip()]
    if not tokens:
        return {"backend": 1, "token_count": 0, "unique_token_ratio": 0.0}
    return {
        "backend": 1,
        "token_count": len(tokens),
        "unique_token_ratio": round(len(set(tokens)) / len(tokens), 6),
    }


def build_reference_source(filename: str, data: bytes, *, weight: float = 1.0) -> ReferenceSourceProfile:
    """Turn one uploaded novel/reference into non-reversible derived features."""
    text = extract_reference_text(filename, data)
    compact_chars = len(re.sub(r"\s+", "", text))
    paragraphs = [p for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    source_id = hashlib.sha256(data).hexdigest()[:24]
    style = analyze_style(text, name=Path(filename).stem or source_id)

    return ReferenceSourceProfile(
        source_id=source_id,
        filename=Path(filename).name,
        weight=max(float(weight), 0.0),
        char_count=compact_chars,
        paragraph_count=len(paragraphs),
        chapter_marker_count=len(_CHAPTER_RE.findall(text)),
        style=style,
        signature_hashes=sorted(build_reference_signature(text)),
        token_stats=_jieba_stats(text),
    )


def build_reference_pack(
    sources: Iterable[tuple[str, bytes, float]],
    *,
    name: str = "reference-pack",
) -> ReferencePack:
    material = list(sources)
    profiles = [build_reference_source(filename, data, weight=weight) for filename, data, weight in material]
    if not profiles:
        raise ValueError("Reference Pack 至少需要一个参考文件")

    weighted_styles = [(profile.style, profile.weight) for profile in profiles if profile.weight > 0]
    if not weighted_styles:
        weighted_styles = [(profile.style, 1.0) for profile in profiles]

    return ReferencePack(
        name=name,
        source_count=len(profiles),
        sources=profiles,
        blended_style=blend_styles(weighted_styles, name=f"{name}-style"),
        story_dna=build_story_dna(material, name=f"{name}-story-dna"),
        notes=[
            "Reference Pack 不保存参考小说正文，只保存派生特征与非可逆签名。",
            "Story DNA 语义抽取将在模型分析层完成；本模块只负责确定性输入与 provenance。",
        ],
    )


def save_reference_pack(pack: ReferencePack, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(pack.model_dump_json(indent=2), encoding="utf-8")
    return target
