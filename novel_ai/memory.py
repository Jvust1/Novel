from __future__ import annotations

from typing import Any

from .models import Character, MemoryExtraction

FORESHADOW_STATUSES = {"planted", "advanced", "resolved"}
FORESHADOW_STATUS_RANK = {"planted": 0, "advanced": 1, "resolved": 2}


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
        chapter_id = str(item.get("chapter_id", "") or "")
        target = by_id.get(str(item.get("id"))) or by_desc.get(str(item.get("description", "")).strip())
        if target:
            old_status = str(target.get("status", "planted") or "planted")
            history = list(target.get("history", []))
            if chapter_id and (not history or history[-1].get("chapter_id") != chapter_id or history[-1].get("status") != status):
                history.append({"chapter_id": chapter_id, "status": status})
            target["history"] = history

            # Once resolved, a later extraction may mention the clue again, but
            # the lifecycle must not silently regress to planted/advanced.
            if FORESHADOW_STATUS_RANK.get(status, 0) >= FORESHADOW_STATUS_RANK.get(old_status, 0):
                target["status"] = status
            else:
                target.setdefault("lifecycle_warnings", []).append({
                    "chapter_id": chapter_id,
                    "attempted_status": status,
                    "kept_status": old_status,
                })
            if item.get("description"):
                target["description"] = item["description"]
            if chapter_id:
                target["last_chapter"] = chapter_id
        else:
            record = {
                "id": str(item.get("id") or f"f{len(existing) + 1}"),
                "description": item.get("description", ""),
                "status": status,
                "planted_chapter": chapter_id,
                "last_chapter": chapter_id,
                "history": [{"chapter_id": chapter_id, "status": status}] if chapter_id else [],
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
    known_misses = {
        (str(row.get("chapter_id")), str(row.get("name")), str(row.get("reason")))
        for row in state["unapplied_updates"]
    }

    def record_miss(name: str, reason: str) -> None:
        key = (extraction.chapter_id, name, reason)
        if key not in known_misses:
            known_misses.add(key)
            state["unapplied_updates"].append(
                {"chapter_id": extraction.chapter_id, "name": name, "reason": reason}
            )

    by_name = {c.name: c for c in characters}
    updated: dict[str, Character] = {}
    for update in extraction.character_updates:
        char = updated.get(update.name) or by_name.get(update.name)
        if char is None:
            record_miss(update.name, "人物不在人物卡中")
            continue
        if char.locked:
            record_miss(update.name, "人物已锁定，回写跳过")
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
    incoming_foreshadowing = []
    for item in extraction.foreshadowing:
        row = item.model_dump()
        if not row.get("chapter_id"):
            row["chapter_id"] = chapter_id
        incoming_foreshadowing.append(row)
    state["foreshadowing"] = _merge_foreshadowing(
        state["foreshadowing"],
        incoming_foreshadowing,
    )
    if extraction.open_threads:
        threads = _dedup(state["open_threads"] + extraction.open_threads)
        state["open_threads"] = threads

    return new_characters, state
