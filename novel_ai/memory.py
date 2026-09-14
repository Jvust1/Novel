from __future__ import annotations

from typing import Any

from .models import Character, MemoryExtraction

FORESHADOW_STATUSES = {"planted", "advanced", "resolved"}


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _merge_foreshadowing(existing: list[dict], incoming: list[dict]) -> list[dict]:
    by_id = {str(item.get("id")): item for item in existing if item.get("id")}
    by_desc = {str(item.get("description", "").strip()): item for item in existing}
    for item in incoming:
        status = item.get("status") if item.get("status") in FORESHADOW_STATUSES else "planted"
        target = by_id.get(str(item.get("id"))) or by_desc.get(str(item.get("description", "")).strip())
        if target:
            target["status"] = status
            if item.get("description"):
                target["description"] = item["description"]
            if item.get("chapter_id"):
                target["last_chapter"] = item["chapter_id"]
        else:
            record = {
                "id": str(item.get("id") or f"f{len(existing) + 1}"),
                "description": item.get("description", ""),
                "status": status,
                "planted_chapter": item.get("chapter_id", ""),
            }
            existing.append(record)
            by_id[record["id"]] = record
            by_desc[record["description"]] = record
    return existing


def apply_extraction(
    characters: list[Character],
    story_state: dict[str, Any],
    extraction: MemoryExtraction,
) -> tuple[list[Character], dict[str, Any]]:
    """Apply one chapter's extracted deltas to character cards and story state.

    Pure function: returns new/updated objects instead of mutating inputs.
    Knowledge boundaries are hard constraints, so gained knowledge is also
    removed from `does_not_know`, and cleared misconceptions leave
    `false_beliefs`.
    """
    state = {
        "facts": list(story_state.get("facts", [])),
        "timeline": list(story_state.get("timeline", [])),
        "foreshadowing": [dict(item) for item in story_state.get("foreshadowing", [])],
        "open_threads": list(story_state.get("open_threads", [])),
        "unapplied_updates": list(story_state.get("unapplied_updates", [])),
    }

    by_name = {c.name: c for c in characters}
    updated: dict[str, Character] = {}
    for update in extraction.character_updates:
        char = updated.get(update.name) or by_name.get(update.name)
        if char is None:
            state["unapplied_updates"].append(
                {"chapter_id": extraction.chapter_id, "name": update.name, "reason": "人物不在人物卡中"}
            )
            continue
        data = char.model_dump()
        if update.goal_change.strip():
            data["current_goal"] = update.goal_change.strip()
        for key, value in update.state_changes.items():
            if str(key).strip() and str(value).strip():
                data.setdefault("status", {})[str(key).strip()] = str(value).strip()
        for other, change in update.relationship_changes.items():
            if str(other).strip() and str(change).strip():
                data.setdefault("relationships", {})[str(other).strip()] = str(change).strip()
        knows = list(data.get("knows", []))
        does_not_know = list(data.get("does_not_know", []))
        for fact in update.knowledge_gained:
            fact = fact.strip()
            if fact and fact not in knows:
                knows.append(fact)
            if fact in does_not_know:
                does_not_know.remove(fact)
        false_beliefs = list(data.get("false_beliefs", []))
        for belief in update.misconceptions_cleared:
            belief = belief.strip()
            if belief in false_beliefs:
                false_beliefs.remove(belief)
            note = f"已确认不成立：{belief}"
            if belief and note not in knows:
                knows.append(note)
        data["knows"] = knows
        data["does_not_know"] = does_not_know
        data["false_beliefs"] = false_beliefs
        resources = list(data.get("resources", []))
        for res in update.resources_gained:
            res = res.strip()
            if res and res not in resources:
                resources.append(res)
        data["resources"] = resources
        if update.recent_change.strip():
            data["recent_change"] = (
                f"[{extraction.chapter_id}] {update.recent_change.strip()}"
                if extraction.chapter_id
                else update.recent_change.strip()
            )
        updated[update.name] = Character.model_validate(data)

    new_characters = [updated.get(c.name, c) for c in characters]
    for name, char in updated.items():
        if name not in by_name:
            new_characters.append(char)

    chapter_id = extraction.chapter_id
    state["facts"] = _dedup(state["facts"] + extraction.new_facts)
    if extraction.timeline_events:
        known_events = {
            (str(item.get("chapter_id")), str(item.get("description")))
            for item in state["timeline"]
        }
        for event in extraction.timeline_events:
            if not event.description.strip():
                continue
            key = (event.chapter_id or chapter_id, event.description)
            if key not in known_events:
                known_events.add(key)
                state["timeline"].append(
                    {"chapter_id": key[0], "description": event.description, "time_hint": event.time_hint}
                )
    state["foreshadowing"] = _merge_foreshadowing(
        state["foreshadowing"],
        [item.model_dump() for item in extraction.foreshadowing],
    )
    if extraction.open_threads:
        threads = _dedup(state["open_threads"] + extraction.open_threads)
        state["open_threads"] = threads

    return new_characters, state
