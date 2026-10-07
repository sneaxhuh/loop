"""Frozen comparisons, human-grounded pilot gates, and explicit pending decisions."""

import copy
from itertools import combinations
from pathlib import Path

from .clients import ApiError, parse_gemini_ranking, parse_qloo_ranking, result_entities
from .fixture import VARIANTS, confirmed, require, resolution_summary, timestamp, validate_fixture, variant_rows
from .metrics import matched_agreement, ranks, spearman, utilities, validate_groups
from .solver import solve_loop, solve_understudy, trade_signature, validate_exchange, validate_program
from .storage import ExperimentError, digest, utcnow, write_json


def resolve_fixture(fixture, qloo, output):
    validate_fixture(fixture)
    resolved = copy.deepcopy(fixture)
    resolved.pop("frozen_hash", None)
    resolved["resolution_options"] = {}
    paused = None
    for entity in resolved["candidates"] + resolved["references"]:
        if confirmed(entity):
            continue
        if paused:
            resolved["resolution_options"][entity["id"]] = {"status": "pending", "reason": paused}
            continue
        evidence_id = None
        try:
            payload, evidence_id, _ = qloo.search(entity)
            options = []
            for item in result_entities(payload):
                options.append({key: item[key] for key in ("entity_id", "name", "types", "subtype", "properties", "external", "disambiguation") if key in item})
            resolved["resolution_options"][entity["id"]] = {"status": "needs_confirmation" if options else "empty",
                                                            "options": options, "evidence_id": evidence_id}
        except (ApiError, ExperimentError) as error:
            resolved["resolution_options"][entity["id"]] = {"status": "empty" if getattr(error, "status", None) == 404 else "error", "reason": str(error),
                                                            "evidence_id": getattr(error, "evidence_id", None) or evidence_id}
            if getattr(error, "status", None) in (401, 403, 429) or qloo.transport.attempts >= qloo.transport.max_requests:
                paused = "Resolution paused after authentication, access, quota, or request-budget failure."
        write_json(output, resolved)
    write_json(output, resolved)
    return resolved


def execute_rankings(fixture, providers, directory):
    validate_fixture(fixture, frozen=True)
    path = Path(directory)
    require(not path.exists() or not any(path.iterdir()), "Use a fresh output directory; existing evidence will not be overwritten.")
    path.mkdir(parents=True, exist_ok=True)
    started = utcnow()
    write_json(path / "fixture.json", fixture)
    candidates = [candidate for candidate in fixture["candidates"] if confirmed(candidate)]
    references = {reference["id"]: reference for reference in fixture["references"]}
    rows = []
    paused = {}
    # Each source receives the same resolved pool, even if a Qloo response is incomplete.
    for profile, variant, reference_ids in variant_rows(fixture):
        selected_refs = [references[value] for value in reference_ids]
        for source in ("qloo", "gemini"):
            row = {"source": source, "profile_id": profile["id"], "variant": variant, "reference_ids": reference_ids,
                   "pool_ids": [candidate["id"] for candidate in candidates], "status": "pending", "groups": []}
            provider = providers.get(source)
            if len(candidates) < 2:
                row["reason"] = "Confirm at least two candidate entities before requesting rankings."
            elif not all(confirmed(reference) for reference in selected_refs):
                row["reason"] = "Reference resolution is incomplete. Both sources must use identical confirmed anchors."
            elif provider is None:
                row["reason"] = source + " credential is missing."
            elif source in paused:
                row["reason"] = paused[source]
            else:
                evidence_id = None
                try:
                    if source == "qloo":
                        payload, evidence_id, _ = provider.rank(candidates, selected_refs, fixture["kind"])
                        parsed = parse_qloo_ranking(payload, candidates)
                    else:
                        payload, evidence_id, _ = provider.rank(candidates, selected_refs)
                        parsed = parse_gemini_ranking(payload, candidates)
                    row.update(parsed, evidence_id=evidence_id, status="ok")
                except (ApiError, ExperimentError) as error:
                    row.update(status="error", reason=str(error), evidence_id=getattr(error, "evidence_id", None) or evidence_id)
                    if getattr(error, "status", None) in (401, 403, 429) or provider.transport.attempts >= provider.transport.max_requests:
                        paused[source] = "Source paused after authentication, access, quota, or request-budget failure."
            rows.append(row)
            write_json(path / "rankings.json", {"version": 1, "mode": "live", "fixture_hash": fixture["frozen_hash"],
                                                "started_at": started, "rows": rows})
    return {"version": 1, "mode": "live", "fixture_hash": fixture["frozen_hash"], "started_at": started, "rows": rows}


def _gate(value, detail, pending=False):
    return {"status": "pending" if pending else ("pass" if value else "fail"), "detail": detail}


def _signature(decision, kind):
    return tuple(sorted(decision.get("selection", []))) if kind == "understudy" else trade_signature(decision.get("moves", []))


def analyze(fixture, recordings, feedback=None):
    validate_fixture(fixture, frozen=True)
    require(recordings.get("fixture_hash") == fixture["frozen_hash"], "Ranking evidence belongs to a different frozen fixture.")
    require(recordings.get("mode") in ("live", "synthetic"), "Evidence must declare live or synthetic mode.")
    started = timestamp(recordings["started_at"])
    feedback = feedback or {}
    expected = {(source, profile["id"], variant) for profile, variant, _ in variant_rows(fixture) for source in ("qloo", "gemini")}
    reference_sets = {(profile["id"], variant): ids for profile, variant, ids in variant_rows(fixture)}
    rows = {}
    for row in recordings.get("rows", []):
        key = (row["source"], row["profile_id"], row["variant"])
        require(key in expected and key not in rows, "Ranking rows contain unexpected or repeated source/profile/variant combinations.")
        require(row.get("reference_ids") == reference_sets[(row["profile_id"], row["variant"])], "Ranking anchors do not match the frozen profile variant.")
        if row.get("status") == "ok":
            if row["groups"] or row["source"] == "gemini":
                validate_groups(row["groups"], row.get("pool_ids", []), complete=row["source"] == "gemini")
            require(set(row.get("pool_ids", [])) == set(resolution_summary(fixture)["resolved"]), "Ranking pool does not match the frozen resolution pool.")
        rows[key] = row
    complete = set(rows) == expected and all(row.get("status") == "ok" for row in rows.values())
    resolved = resolution_summary(fixture)
    pool = set(resolved["resolved"])
    if complete:
        for row in rows.values():
            pool &= set(ranks(row["groups"]))
    else:
        pool = set()
    synthetic = recordings["mode"] != "live"
    resolution_measured = all(confirmed(candidate) or candidate.get("resolution_status") == "unresolved"
                              or fixture.get("resolution_options", {}).get(candidate["id"], {}).get("status") == "empty"
                              for candidate in fixture["candidates"])
    gates = {"candidate_resolution": _gate(resolved["fraction"] >= 0.8, resolved, pending=synthetic or not resolution_measured),
             "common_pool": _gate(len(pool) >= 8, {"ids": sorted(pool), "size": len(pool), "excluded": sorted(set(resolved["resolved"]) - pool)}, pending=synthetic or not complete)}
    correlations = []
    if complete:
        for variant in VARIANTS:
            for first, second in combinations(fixture["profiles"], 2):
                a, b = rows[("qloo", first["id"], variant)], rows[("qloo", second["id"], variant)]
                correlation = spearman(a["groups"], b["groups"], pool)
                correlations.append({"variant": variant, "profiles": [first["id"], second["id"]], **(correlation or {"rho": None, "compared": 0})})
    # Count distinct profile pairs, not repeated versions of the same pair.
    differing_pairs = {tuple(value["profiles"]) for value in correlations if value["rho"] is not None and value["rho"] <= 0.60}
    gates["contrasting_profiles"] = _gate(len(differing_pairs) >= 2, {"distinct_pairs": [list(value) for value in sorted(differing_pairs)], "correlations": correlations}, pending=synthetic or not complete)
    cross_domain = []
    if complete:
        for profile in fixture["profiles"]:
            base = ranks(rows[("qloo", profile["id"], "music_only")]["groups"], pool)
            for variant in VARIANTS[1:]:
                changed = base != ranks(rows[("qloo", profile["id"], variant)]["groups"], pool)
                cross_domain.append({"profile_id": profile["id"], "variant": variant, "ordering_changed": changed})
    gates["cross_domain_change"] = _gate(any(value["ordering_changed"] for value in cross_domain), cross_domain, pending=synthetic or not complete)
    decisions = []
    withdrawal = None
    if complete and len(pool) >= 2:
        variants = list(VARIANTS)
        if all("declared" in profile["variants"] for profile in fixture["profiles"]):
            variants.append("declared")
        for method in ("ordinal", "reciprocal"):
            for variant in variants:
                for source in ("qloo", "gemini"):
                    matrix = {profile["id"]: utilities(rows[(source, profile["id"], variant)]["groups"], pool, method) for profile in fixture["profiles"]}
                    if fixture["kind"] == "understudy":
                        proposal = solve_understudy(fixture, matrix, pool, recordings["started_at"])
                        validation = validate_program(fixture, proposal, pool, matrix, recordings["started_at"])
                    else:
                        proposal = solve_loop(fixture, matrix, pool)
                        validation = validate_exchange(fixture, proposal, pool, matrix)
                    proposal_id = digest({"fixture_hash": fixture["frozen_hash"], "source": source, "variant": variant, "utility": method, "decision": proposal})[:16]
                    decisions.append({"proposal_id": proposal_id, "source": source, "variant": variant, "utility": method,
                                      "proposal": proposal, "validation": validation, "matrix": matrix})
                    if fixture["kind"] == "loop" and source == "qloo" and method == "ordinal" and variant == "declared" and proposal.get("moves"):
                        removed = proposal["moves"][0]["candidate_id"]
                        repaired = solve_loop(fixture, matrix, pool, withdrawn=[removed])
                        checked = validate_exchange(fixture, repaired, pool, matrix, withdrawn=[removed])
                        withdrawal = {"kind": "injected_withdrawal_of_offered_copy", "inventory_provenance": fixture["provenance"],
                                      "withdrawn_id": removed, "proposal": repaired, "validation": checked}
    comparisons = []
    for variant in VARIANTS:
        matches = {value["source"]: value for value in decisions if value["variant"] == variant and value["utility"] == "ordinal"}
        if len(matches) == 2:
            qloo, gemini = matches["qloo"], matches["gemini"]
            valid = qloo["validation"]["valid"] and gemini["validation"]["valid"]
            changed = _signature(qloo["proposal"], fixture["kind"]) != _signature(gemini["proposal"], fixture["kind"])
            has_action = qloo["proposal"]["status"] == "proposed" or gemini["proposal"]["status"] == "proposed"
            comparisons.append({"variant": variant, "decision_changed": changed and valid and has_action,
                                "qloo_proposal_id": qloo["proposal_id"], "gemini_proposal_id": gemini["proposal_id"]})
    gates["decision_change"] = _gate(any(value["decision_changed"] for value in comparisons), comparisons, pending=synthetic or not complete)
    gates["operational_validity"] = _gate(bool(decisions) and all(value["validation"]["valid"] for value in decisions),
                                          {"checked": len(decisions)}, pending=synthetic or not complete)
    human_results = []
    if fixture["kind"] == "understudy":
        organizer = fixture["provenance"] == "organizer" and fixture.get("organizer_inputs_attested") is True
        gates["credible_organizer_inputs"] = _gate(organizer, "Organizer-sourced roster and constraints are required for product selection.", pending=not organizer or synthetic)
    else:
        real_inventory = fixture["provenance"] == "participant_inventory" and fixture.get("inventory_attested") is True
        gates["real_inventory"] = _gate(real_inventory, "Actual offered copies must be attested by their owners.", pending=not real_inventory or synthetic)
        ground_truth_complete = True
        for participant in fixture["participants"]:
            profile_id = participant["profile_id"]
            qloo = rows.get(("qloo", profile_id, "declared"), {})
            gemini = rows.get(("gemini", profile_id, "declared"), {})
            human_order = participant.get("human_ranking", [])
            recorded = participant.get("ranking_recorded_at")
            ready = (participant.get("references_attested") is True and set(human_order) == {candidate["id"] for candidate in fixture["candidates"]}
                     and recorded is not None and timestamp(recorded) <= started and qloo.get("status") == gemini.get("status") == "ok")
            agreement = matched_agreement(qloo["groups"], gemini["groups"], human_order) if ready else None
            if agreement is None or agreement["compared"] < 28:
                ground_truth_complete = False
            human_results.append({"participant_id": participant["id"], "status": "measured" if agreement else "pending", **(agreement or {})})
        wins = sum(value.get("qloo", 0) > value.get("gemini", 0) for value in human_results if value["status"] == "measured")
        gates["human_preference_advantage"] = _gate(wins >= 3, {"participant_wins": wins, "participants": human_results,
                                                               "note": "Anticipated reading interest, not satisfaction after reading. At least 28 identical untied pairs per participant."},
                                                  pending=synthetic or not ground_truth_complete)
        declared = next((value for value in decisions if value["source"] == "qloo" and value["variant"] == "declared" and value["utility"] == "ordinal"), None)
        accepted_cycle = False
        missing_reviews = True
        if declared:
            review = feedback.get("loop_acceptance", {}).get(declared["proposal_id"], {})
            reviewed_at = review.get("recorded_at")
            approvals = review.get("participants", {})
            valid_review = reviewed_at is not None and timestamp(reviewed_at) >= started
            long_cycles = [cycle for cycle in declared["proposal"].get("cycles", []) if len(cycle) >= 3]
            for cycle in long_cycles:
                members = {move["from"] for move in cycle}
                answered = valid_review and all(isinstance(approvals.get(person, {}).get("accepted"), bool)
                                                and isinstance(approvals.get(person, {}).get("reason"), str) for person in members)
                if answered:
                    missing_reviews = False
                    accepted_cycle |= all(approvals[person]["accepted"] for person in members)
            if not long_cycles:
                missing_reviews = False
        gates["accepted_multilateral_exchange"] = _gate(accepted_cycle, {"proposal_id": declared["proposal_id"] if declared else None},
                                                         pending=synthetic or declared is None or missing_reviews)
        gates["withdrawal_repair"] = _gate(withdrawal is not None and withdrawal["validation"]["valid"], withdrawal,
                                           pending=synthetic or declared is None)
    sensitivity = []
    for value in decisions:
        if value["utility"] != "ordinal":
            continue
        alternate = next(item for item in decisions if item["source"] == value["source"] and item["variant"] == value["variant"] and item["utility"] == "reciprocal")
        sensitivity.append({"source": value["source"], "variant": value["variant"],
                            "selection_changed": _signature(value["proposal"], fixture["kind"]) != _signature(alternate["proposal"], fixture["kind"])})
    statuses = [gate["status"] for gate in gates.values()]
    mechanism_names = ("candidate_resolution", "common_pool", "contrasting_profiles", "cross_domain_change", "decision_change", "operational_validity")
    mechanism_statuses = [gates[key]["status"] for key in mechanism_names]
    mechanism = "fail" if "fail" in mechanism_statuses else ("pending" if "pending" in mechanism_statuses else "pass")
    selection = "no_go" if "fail" in statuses else ("pending" if "pending" in statuses else "eligible")
    return {"version": 1, "fixture_id": fixture["id"], "fixture_hash": fixture["frozen_hash"], "kind": fixture["kind"],
            "mode": recordings["mode"], "started_at": recordings["started_at"], "generated_at": utcnow(),
            "mechanism": mechanism, "selection": selection, "gates": gates, "common_pool": sorted(pool), "decisions": decisions,
            "comparisons": comparisons, "sensitivity": sensitivity, "human_results": human_results,
            "ranking_failures": [row for row in rows.values() if row.get("status") != "ok"],
            "missing_rows": [list(key) for key in sorted(expected - set(rows))],
            "limitations": ["Synthetic runs cannot pass live viability gates.", "Rank-based fit and regret are application-defined relative indices.",
                            "Human rankings measure anticipated interest; the small pilot does not establish statistical superiority.",
                            "A proposed exchange is not a completed physical transfer."]}


def select_project(reports):
    by_kind = {report["kind"]: report for report in reports}
    if by_kind.get("loop", {}).get("selection") == "eligible":
        return {"decision": "loop", "reason": "Loop passed the shared mechanism, real inventory, human preference, acceptance, and repair gates."}
    if by_kind.get("understudy", {}).get("selection") == "eligible":
        return {"decision": "understudy", "reason": "Understudy passed the mechanism gates with credible organizer inputs."}
    if any(report["selection"] == "pending" for report in reports) or set(by_kind) != {"loop", "understudy"}:
        return {"decision": "pending", "reason": "Collect missing live evidence or real inputs before committing to a product."}
    return {"decision": "reopen_ideation", "reason": "Neither tested concept passed the preregistered gates."}
