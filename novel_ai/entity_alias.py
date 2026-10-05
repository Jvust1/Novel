"""Optional RapidFuzz entity alias consistency checks.

Upstream: rapidfuzz/RapidFuzz @
db6e504539a9c895180b266a06b36a32cb6029ee (MIT).

The matcher receives entity mentions extracted elsewhere and only decides
whether a near-match is likely a typo/alias drift against canonical names.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class EntityAliasAlert:
    observed: str
    canonical: str
    score: float
    matched_alias: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RapidFuzzEntityMatcher:
    """Map observed names to canonical entities using RapidFuzz extractOne()."""

    def __init__(self, *, process_module: Any | None = None, scorer: Any | None = None) -> None:
        if process_module is None or scorer is None:
            try:
                from rapidfuzz import fuzz, process
            except ImportError as exc:
                raise RuntimeError(
                    "RapidFuzz is optional; install requirements-extras/nlp.txt"
                ) from exc
            process_module = process_module or process
            scorer = scorer or fuzz.WRatio
        if not callable(getattr(process_module, "extractOne", None)):
            raise TypeError("process_module must provide extractOne()")
        if not callable(scorer):
            raise TypeError("scorer must be callable")
        self._process = process_module
        self._scorer = scorer

    def find_drift(
        self,
        observed_entities: Sequence[str],
        canonical_aliases: Mapping[str, Sequence[str]],
        *,
        threshold: float = 86.0,
    ) -> list[EntityAliasAlert]:
        if not 0.0 <= float(threshold) <= 100.0:
            raise ValueError("threshold must be in [0, 100]")

        choice_to_canonical: dict[str, str] = {}
        for canonical, aliases in canonical_aliases.items():
            name = str(canonical).strip()
            if not name:
                continue
            choice_to_canonical[name] = name
            for alias in aliases:
                value = str(alias).strip()
                if value:
                    choice_to_canonical[value] = name

        choices = list(choice_to_canonical)
        exact = set(choices)
        alerts: list[EntityAliasAlert] = []
        for raw in observed_entities:
            observed = str(raw).strip()
            if not observed or observed in exact or not choices:
                continue
            match = self._process.extractOne(
                observed,
                choices,
                scorer=self._scorer,
                score_cutoff=float(threshold),
            )
            if not match:
                continue
            matched_alias = str(match[0])
            score = float(match[1])
            alerts.append(
                EntityAliasAlert(
                    observed=observed,
                    canonical=choice_to_canonical[matched_alias],
                    score=round(score, 4),
                    matched_alias=matched_alias,
                )
            )

        alerts.sort(key=lambda item: (-item.score, item.observed, item.canonical))
        return alerts
