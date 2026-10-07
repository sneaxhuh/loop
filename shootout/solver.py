"""Exact small-pool solvers shared by both ranking sources."""

from itertools import combinations, permutations, product

from .fixture import timestamp
from .storage import utcnow


def program_fit(ids, matrix):
    return {profile: max((values[value] for value in ids if value in values), default=0) for profile, values in matrix.items()}


def operational_programs(fixture, pool, now=None):
    constraints = fixture["constraints"]
    clock = timestamp(now or utcnow())
    candidates = [candidate for candidate in fixture["candidates"]
                  if candidate["id"] in pool and candidate["available"]
                  and (not candidate.get("offer_expires_at") or timestamp(candidate["offer_expires_at"]) > clock)
                  and set(candidate.get("equipment", [])) <= set(constraints.get("equipment", []))
                  and candidate["id"] not in constraints.get("original_ids", [])]
    results = []
    for length in (1, 2):
        for ordered in permutations(candidates, length):
            cost = sum(candidate["fee_units"] for candidate in ordered)
            performance = sum(candidate["duration_minutes"] for candidate in ordered)
            if cost > constraints["budget_units"] or performance < constraints["min_performance_minutes"]:
                continue
            elapsed, schedule = 0, []
            for candidate in ordered:
                end = elapsed + candidate["duration_minutes"]
                if elapsed < candidate["available_from"] or end > candidate["available_until"]:
                    break
                schedule.append({"candidate_id": candidate["id"], "start_minute": elapsed, "end_minute": end})
                elapsed = end + constraints["changeover_minutes"]
            else:
                actual_length = elapsed - constraints["changeover_minutes"]
                if actual_length <= constraints["slot_minutes"]:
                    results.append({"selection": [candidate["id"] for candidate in ordered], "cost_units": cost,
                                    "duration_minutes": actual_length, "schedule": schedule})
    return results


def solve_understudy(fixture, matrix, pool, now=None):
    feasible = operational_programs(fixture, pool, now)
    floor = fixture["constraints"].get("fit_floor", 0.5)
    weights = {profile["id"]: profile.get("weight", 1) for profile in fixture["profiles"]}
    previous = set(fixture["constraints"].get("previous_ids", []))
    ideal = {profile: max((program_fit(program["selection"], matrix)[profile] for program in feasible), default=0) for profile in matrix}
    scored = []
    for program in feasible:
        fit = program_fit(program["selection"], matrix)
        mean = sum(weights[profile] * value for profile, value in fit.items()) / sum(weights[profile] for profile in fit)
        scored.append(dict(program, fit=fit, worst_fit=min(fit.values()), mean_fit=mean,
                           changes=len(previous.symmetric_difference(program["selection"])) if previous else 0))
    eligible = [program for program in scored if program["worst_fit"] >= floor]
    if not eligible:
        return {"status": "infeasible", "selection": [], "operationally_feasible": len(feasible), "meeting_fit_floor": 0,
                "individual_ideal": ideal, "reason": "No program meets all operational constraints and declared fit floors."}
    best = min(eligible, key=lambda program: (-program["worst_fit"], -program["mean_fit"], program["changes"], program["cost_units"], tuple(program["selection"])))
    regret = {profile: max(0, ideal[profile] - best["fit"][profile]) for profile in matrix}
    frontier = [program for program in scored if not any(other["cost_units"] <= program["cost_units"] and other["worst_fit"] >= program["worst_fit"]
                and (other["cost_units"] < program["cost_units"] or other["worst_fit"] > program["worst_fit"]) for other in scored)]
    unique_frontier = {(program["cost_units"], program["worst_fit"]): {"cost_units": program["cost_units"], "worst_fit": program["worst_fit"]} for program in frontier}
    original_ids = fixture["constraints"].get("original_ids", [])
    original_fit = program_fit(original_ids, matrix) if original_ids and set(original_ids) <= set(pool) else None
    return dict(best, status="proposed", operationally_feasible=len(feasible), meeting_fit_floor=len(eligible),
                individual_ideal=ideal, regret=regret, original_fit=original_fit,
                frontier=[unique_frontier[key] for key in sorted(unique_frontier)])


def validate_program(fixture, proposal, pool, matrix, now=None):
    if proposal["status"] == "infeasible":
        return {"valid": proposal.get("selection") == [], "violations": [] if not proposal.get("selection") else ["Infeasible proposal has a selection."]}
    permitted = {tuple(program["selection"]): program for program in operational_programs(fixture, pool, now)}
    program = permitted.get(tuple(proposal.get("selection", [])))
    violations = []
    if not program:
        violations.append("Selection violates availability, cost, duration, equipment, expiry, or protected-original constraints.")
    elif any(proposal.get(key) != program[key] for key in ("cost_units", "schedule", "duration_minutes")):
        violations.append("Published cost or schedule does not match the selected acts.")
    if program and any(value < fixture["constraints"].get("fit_floor", 0.5) for value in program_fit(program["selection"], matrix).values()):
        violations.append("Selection violates a declared fit floor.")
    return {"valid": not violations, "violations": violations}


def trade_edges(fixture, matrix, pool, withdrawn=()):
    result = {}
    for candidate in fixture["candidates"]:
        if candidate["id"] not in pool or not candidate["available"] or not candidate["offered"] or candidate["id"] in withdrawn:
            continue
        for participant in fixture["participants"]:
            person = participant["id"]
            if person == candidate["owner"] or candidate["id"] in participant.get("already_read_ids", []):
                continue
            if participant.get("languages") and candidate["language"] not in participant["languages"]:
                continue
            if "acceptable_ids" in participant and candidate["id"] not in participant["acceptable_ids"]:
                continue
            utility = matrix[participant["profile_id"]][candidate["id"]]
            if utility >= fixture["constraints"].get("fit_floor", 0.5):
                result[(candidate["id"], person)] = utility
    return result


def trade_signature(moves):
    return tuple(sorted((move["from"], move["to"], move["candidate_id"]) for move in moves))


def pareto_insert(states, state):
    """Preserve min-fit / total-fit tradeoffs: lexicographic DP alone is unsound."""
    for existing in states:
        if existing["worst_fit"] >= state["worst_fit"] and existing["total_fit"] >= state["total_fit"]:
            if (existing["worst_fit"], existing["total_fit"]) != (state["worst_fit"], state["total_fit"]) or trade_signature(existing["moves"]) <= trade_signature(state["moves"]):
                return
    states[:] = [existing for existing in states if not (state["worst_fit"] >= existing["worst_fit"] and state["total_fit"] >= existing["total_fit"])]
    states.append(state)


def solve_loop(fixture, matrix, pool, withdrawn=()):
    participants = sorted(participant["id"] for participant in fixture["participants"])
    bits = {person: 1 << index for index, person in enumerate(participants)}
    offers = {person: [candidate for candidate in fixture["candidates"] if candidate["owner"] == person
                     and candidate["id"] in pool and candidate["available"] and candidate["offered"] and candidate["id"] not in withdrawn]
              for person in participants}
    edges = trade_edges(fixture, matrix, pool, withdrawn)
    cycles = {}
    total_cycles = 0
    for length in range(2, fixture["constraints"].get("max_cycle_length", 4) + 1):
        for owners in combinations(participants, length):
            mask = sum(bits[person] for person in owners)
            for rest in permutations(owners[1:]):
                ordered = (owners[0],) + rest
                for books in product(*(offers[person] for person in ordered)):
                    moves = [{"from": person, "to": ordered[(index + 1) % length], "candidate_id": books[index]["id"]} for index, person in enumerate(ordered)]
                    if not all((move["candidate_id"], move["to"]) in edges for move in moves):
                        continue
                    fit = {move["to"]: edges[(move["candidate_id"], move["to"])] for move in moves}
                    cycle = {"moves": moves, "fit": fit, "worst_fit": min(fit.values()), "total_fit": sum(fit.values()), "cycles": [moves]}
                    total_cycles += 1
                    pareto_insert(cycles.setdefault(mask, []), cycle)
    states = {0: [{"moves": [], "fit": {}, "worst_fit": 1, "total_fit": 0, "cycles": []}]}
    for mask in range(1 << len(participants)):
        for state in list(states.get(mask, [])):
            for cycle_mask, options in cycles.items():
                if cycle_mask & mask:
                    continue
                for cycle in options:
                    combined = {"moves": state["moves"] + cycle["moves"], "fit": dict(state["fit"], **cycle["fit"]),
                                "worst_fit": min(state["worst_fit"], cycle["worst_fit"]), "total_fit": state["total_fit"] + cycle["total_fit"],
                                "cycles": state["cycles"] + cycle["cycles"]}
                    pareto_insert(states.setdefault(mask | cycle_mask, []), combined)
    choices = [state for options in states.values() for state in options if state["moves"]]
    if not choices:
        return {"status": "no_exchange", "moves": [], "cycles": [], "fit": {}, "feasible_cycles": total_cycles,
                "unmatched": participants, "reason": "No closed exchange meets availability, language, read-history, and fit constraints."}
    best = min(choices, key=lambda state: (-len(state["fit"]), -state["worst_fit"], -state["total_fit"], trade_signature(state["moves"])))
    return dict(best, status="proposed", feasible_cycles=total_cycles, unmatched=sorted(set(participants) - set(best["fit"])))


def validate_exchange(fixture, proposal, pool, matrix, withdrawn=()):
    candidates = {candidate["id"]: candidate for candidate in fixture["candidates"]}
    people = {participant["id"] for participant in fixture["participants"]}
    edges = trade_edges(fixture, matrix, pool, withdrawn)
    moves = proposal.get("moves", [])
    violations = []
    outgoing, incoming, used = set(), set(), set()
    for move in moves:
        candidate = candidates.get(move.get("candidate_id"))
        sender, receiver = move.get("from"), move.get("to")
        if not candidate or candidate["owner"] != sender or sender not in people or receiver not in people:
            violations.append("Unknown copy, participant, or incorrect owner.")
        if sender in outgoing or receiver in incoming or move.get("candidate_id") in used:
            violations.append("A participant or physical copy is used more than once.")
        if (move.get("candidate_id"), receiver) not in edges:
            violations.append("A handoff violates declared exchange constraints.")
        outgoing.add(sender)
        incoming.add(receiver)
        used.add(move.get("candidate_id"))
    if outgoing != incoming:
        violations.append("Handoffs do not form closed one-for-one exchanges.")
    if proposal.get("status") == "no_exchange" and moves:
        violations.append("A no-exchange result contains handoffs.")
    if proposal.get("status") == "proposed" and not moves:
        violations.append("An exchange proposal contains no handoffs.")
    actual_moves = [move for cycle in proposal.get("cycles", []) for move in cycle]
    if trade_signature(actual_moves) != trade_signature(moves):
        violations.append("Displayed cycles do not match the proposed handoffs.")
    for cycle in proposal.get("cycles", []):
        if not 2 <= len(cycle) <= fixture["constraints"].get("max_cycle_length", 4):
            violations.append("Exchange cycle exceeds the configured size.")
        if any(cycle[index].get("to") != cycle[(index + 1) % len(cycle)].get("from") for index in range(len(cycle))):
            violations.append("Displayed cycle is not closed.")
    return {"valid": not violations, "violations": sorted(set(violations))}
