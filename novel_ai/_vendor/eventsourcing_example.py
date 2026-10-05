"""Small licensed event/projection kernel adapted for Novel.

Derived from pyeventsourcing/eventsourcing at
575d42c10a821828639b90178ed56703abe9c9f1 (BSD-3-Clause).
Copyright (c) 2025, John Bywater. All rights reserved.
See third_party/eventsourcing/LICENSE, NOTICE.md, and provenance.json.

Pydantic freezing is shallow. Callers must detach and validate nested payloads;
this module neither authorizes events nor supplies persistence or tamper proofing.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field


class Immutable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DomainEvent(Immutable):
    originator_id: str = Field(min_length=1)
    originator_version: int = Field(ge=1)
    timestamp: datetime


class Aggregate(Immutable):
    id: str = Field(min_length=1)
    version: int = Field(ge=0)
    created_on: datetime
    modified_on: datetime


class ProjectionError(ValueError):
    """An event stream or mutator result cannot be replayed safely."""


class OriginatorIDError(ProjectionError):
    """The event belongs to a different aggregate."""


class OriginatorVersionError(ProjectionError):
    """The event is not the next version in the aggregate's sequence."""


TAggregate = TypeVar("TAggregate", bound=Aggregate)
MutatorFunction = Callable[[DomainEvent, TAggregate | None], TAggregate | None]


def check_event_order(event: DomainEvent, aggregate: Aggregate | None) -> None:
    """Port of CanMutateAggregate.mutate's identity and next-version guards."""
    if aggregate is None:
        next_version = 1
    else:
        # Check this event belongs to this aggregate.
        if event.originator_id != aggregate.id:
            raise OriginatorIDError(event.originator_id, aggregate.id)
        next_version = aggregate.version + 1
    # Check this event is the next in its sequence.
    if event.originator_version != next_version:
        raise OriginatorVersionError(event.originator_version, next_version)


def aggregate_projector(
    mutator: MutatorFunction[TAggregate],
) -> Callable[[TAggregate | None, Iterable[DomainEvent]], TAggregate | None]:
    """Replay in supplied order; reject mismatches rather than sorting events."""
    def project_aggregate(
        aggregate: TAggregate | None, events: Iterable[DomainEvent]
    ) -> TAggregate | None:
        for event in events:
            if not isinstance(event, DomainEvent):
                raise ProjectionError("events must be validated DomainEvent instances")
            check_event_order(event, aggregate)
            projected = mutator(event, aggregate)
            if not isinstance(projected, Aggregate):
                raise ProjectionError("mutator must return an Aggregate for every event")
            if projected.id != event.originator_id:
                raise OriginatorIDError(projected.id, event.originator_id)
            if projected.version != event.originator_version:
                raise OriginatorVersionError(projected.version, event.originator_version)
            aggregate = projected
        return aggregate

    return project_aggregate
