"""Validate the intentionally small JSON experiment contract."""

import math
import re
import uuid
from datetime import datetime

from .storage import ExperimentError, fixture_hash

VARIANTS = ("music_only", "music_movies", "music_brands")
TYPES = {"artist", "book", "movie", "brand", "podcast", "tv_show", "video_game", "person", "place", "destination"}


def require(condition, message):
    if not condition:
        raise ExperimentError(message)


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.tzinfo is not None, "Timestamps must include a timezone.")
        return result
    except (TypeError, AttributeError, ValueError):
        raise ExperimentError("Invalid timezone-aware timestamp: %r" % value)


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value) is not None


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def confirmed(entity):
    return bool(entity.get("qloo_id") and entity.get("confirmed") is True)


def validate_fixture(fixture, frozen=False):
    require(isinstance(fixture, dict) and fixture.get("version") == 1, "Fixture version must be 1.")
    kind = fixture.get("kind")
    require(kind in ("understudy", "loop"), "Fixture kind must be understudy or loop.")
    require(identifier(fixture.get("id")), "Fixture needs a safe id.")
    require(fixture.get("provenance") in ("synthetic_test", "organizer", "participant_inventory"), "Declare fixture provenance.")
    candidates = fixture.get("candidates", [])
    references = fixture.get("references", [])
    profiles = fixture.get("profiles", [])
    require(isinstance(candidates, list) and 1 <= len(candidates) <= 20, "Supply 1–20 candidates; the pilot target is 12–20 books or 15–20 artists.")
    require(isinstance(references, list) and references, "Supply public cultural references.")
    require(isinstance(profiles, list) and len(profiles) == 4, "Supply exactly four contrasting experiment profiles.")
    ids = set()
    qloo_ids = set()
    for entity in candidates + references:
        require(isinstance(entity, dict) and identifier(entity.get("id")), "Every entity needs a safe local id.")
        require(entity["id"] not in ids, "Entity ids must be unique: " + entity["id"])
        ids.add(entity["id"])
        require(isinstance(entity.get("name"), str) and entity["name"].strip(), "Every entity needs a public title/name.")
        require(entity.get("type") in TYPES, "Unsupported entity type: " + str(entity.get("type")))
        if entity.get("qloo_id"):
            try:
                uuid.UUID(entity["qloo_id"])
            except (ValueError, AttributeError, TypeError):
                raise ExperimentError("qloo_id must be a UUID for " + entity["id"])
        if "confirmed" in entity:
            require(isinstance(entity["confirmed"], bool), "confirmed must be boolean.")
    expected_type = "artist" if kind == "understudy" else "book"
    for candidate in candidates:
        require(candidate["type"] == expected_type, "Candidate types must match the experiment.")
        require(isinstance(candidate.get("available"), bool), "Declare available for " + candidate["id"])
        if confirmed(candidate):
            qid = candidate["qloo_id"].lower()
            require(qid not in qloo_ids, "Two candidates resolve to the same Qloo work/entity. Use distinct titles in this sprint.")
            qloo_ids.add(qid)
        if candidate.get("offer_expires_at"):
            timestamp(candidate["offer_expires_at"])
    refs = {reference["id"]: reference for reference in references}
    profile_ids = set()
    for profile in profiles:
        require(identifier(profile.get("id")) and profile["id"] not in profile_ids, "Profile ids must be unique.")
        profile_ids.add(profile["id"])
        variants = profile.get("variants", {})
        require(isinstance(variants, dict), "Profile variants must be an object.")
        require(set(VARIANTS) <= set(variants), "Every profile needs the three experimental variants.")
        require(set(variants) <= set(VARIANTS) | {"declared"}, "Unknown profile variant.")
        for variant, values in variants.items():
            require(isinstance(values, list) and values and len(values) == len(set(values)), "Each variant needs distinct reference ids.")
            require(all(value in refs for value in values), "A profile references an unknown cultural entity.")
            types = {refs[value]["type"] for value in values}
            allowed = {"artist"} if variant == "music_only" else ({"artist", "movie"} if variant == "music_movies" else {"artist", "brand"})
            if variant != "declared":
                require(types <= allowed and allowed <= types, "Reference domains do not match " + variant)
                require(set(variants["music_only"]) <= set(values), "Mixed variants must retain the same music anchors.")
        weight = profile.get("weight", 1)
        require(finite_number(weight) and weight > 0, "Profile weights must be positive.")
    constraints = fixture.get("constraints", {})
    require(isinstance(constraints, dict), "Constraints must be an object.")
    fit_floor = constraints.get("fit_floor", 0.5)
    require(finite_number(fit_floor) and 0 <= fit_floor <= 1, "fit_floor must be between 0 and 1.")
    candidate_ids = {candidate["id"] for candidate in candidates}
    if kind == "understudy":
        for key in ("budget_units", "slot_minutes", "min_performance_minutes", "changeover_minutes"):
            require(isinstance(constraints.get(key), int) and not isinstance(constraints.get(key), bool) and constraints[key] >= 0, "Declare nonnegative integer " + key)
        require(constraints["slot_minutes"] > 0, "slot_minutes must be positive.")
        require(isinstance(constraints.get("equipment", []), list), "Equipment must be a list.")
        require(set(constraints.get("original_ids", [])) <= candidate_ids, "Unknown original artist.")
        for candidate in candidates:
            for key in ("fee_units", "duration_minutes"):
                require(isinstance(candidate.get(key), int) and not isinstance(candidate.get(key), bool) and candidate[key] >= 0, "Declare integer " + key + " for " + candidate["id"])
            require(candidate["duration_minutes"] > 0, "Performance durations must be positive.")
            require(isinstance(candidate.get("equipment", []), list), "Artist equipment must be a list.")
            for key in ("available_from", "available_until"):
                require(finite_number(candidate.get(key)), "Declare availability window " + key)
            require(candidate["available_from"] <= candidate["available_until"], "Invalid availability window.")
    else:
        participants = fixture.get("participants", [])
        require(isinstance(participants, list) and len(participants) == 4, "Loop needs four anonymous participants.")
        owner_ids = set()
        assigned_profiles = set()
        for participant in participants:
            require(identifier(participant.get("id")) and participant["id"] not in owner_ids, "Participant ids must be unique.")
            owner_ids.add(participant["id"])
            require(participant.get("profile_id") in profile_ids and participant["profile_id"] not in assigned_profiles, "Give each participant their own profile.")
            assigned_profiles.add(participant["profile_id"])
            for key in ("acceptable_ids", "already_read_ids", "human_ranking"):
                if key in participant:
                    values = participant[key]
                    require(isinstance(values, list) and len(values) == len(set(values)) and set(values) <= candidate_ids, "Invalid " + key + " for " + participant["id"])
            require(isinstance(participant.get("languages", []), list), "Languages must be a list.")
            if participant.get("ranking_recorded_at"):
                timestamp(participant["ranking_recorded_at"])
        for candidate in candidates:
            require(candidate.get("owner") in owner_ids, "Declare the actual anonymous owner of " + candidate["id"])
            require(isinstance(candidate.get("offered"), bool), "Declare offered for " + candidate["id"])
            require(isinstance(candidate.get("language"), str) and candidate["language"], "Declare book language.")
        maximum = constraints.get("max_cycle_length", 4)
        require(isinstance(maximum, int) and 2 <= maximum <= 4, "max_cycle_length must be 2–4.")
    if frozen:
        require(fixture.get("frozen_hash") == fixture_hash(fixture), "Fixture is not frozen or changed after freezing. Freeze a new experiment.")
    return fixture


def resolution_summary(fixture):
    resolved = [candidate["id"] for candidate in fixture["candidates"] if confirmed(candidate)]
    return {"total": len(fixture["candidates"]), "resolved": resolved,
            "unresolved": [candidate["id"] for candidate in fixture["candidates"] if not confirmed(candidate)],
            "fraction": len(resolved) / len(fixture["candidates"])}


def variant_rows(fixture):
    return [(profile, variant, ids) for profile in fixture["profiles"] for variant, ids in profile["variants"].items()]

