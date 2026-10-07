"""Blinded 10-case × 5-reviewer packs with honest partial-results reporting."""

import csv
import random
from pathlib import Path

from .fixture import require
from .storage import read_json, write_json


def review_pack(manifest_path, output, seed=7):
    manifest_path = Path(manifest_path)
    manifest = read_json(manifest_path)
    cases = manifest.get("cases", [])
    require(len(cases) == 10 and len({case["id"] for case in cases}) == 10, "Supply ten distinct evaluation cases.")
    required_counts = {"straightforward": 3, "conflicting": 3, "cross_domain": 2, "disruption": 2}
    require({category: sum(case["category"] == category for case in cases) for category in required_counts} == required_counts,
            "Use 3 straightforward, 3 conflicting, 2 cross-domain, and 2 disruption cases.")
    output = Path(output)
    require(not output.exists() or not any(output.iterdir()), "Use a fresh reviewer-pack directory.")
    output.mkdir(parents=True, exist_ok=True)
    chooser = random.Random(seed)
    loaded = []
    for case in cases:
        require(bool(case.get("report_path")), "Fill report_path for " + case["id"])
        run = manifest_path.parent / case["report_path"]
        report, fixture = read_json(run / "report.json"), read_json(run / "fixture.json")
        decisions = {value["source"]: value for value in report["decisions"] if value["variant"] == case["variant"] and value["utility"] == "ordinal"}
        require(set(decisions) == {"qloo", "gemini"}, "Case needs both matched decisions: " + case["id"])
        require(all(value["validation"]["valid"] for value in decisions.values()), "Cannot review invalid decisions.")
        candidates = [{key: item[key] for key in ("id", "name", "author", "neutral_description", "owner", "fee_units", "duration_minutes", "language") if key in item} for item in fixture["candidates"]]
        refs = {value["id"]: value for value in fixture["references"]}
        public_profiles = [{"profile_id": profile["id"], "references": [{"name": refs[value]["name"], "type": refs[value]["type"]}
                            for value in profile["variants"][case["variant"]]]} for profile in fixture["profiles"]]
        loaded.append((case, decisions, candidates, fixture["constraints"], report["mode"], fixture["provenance"], public_profiles))
    mapping = []
    for reviewer_index in range(5):
        reviewer = "reviewer-%d" % (reviewer_index + 1)
        order = list(loaded)
        chooser.shuffle(order)
        pack = []
        for case, decisions, candidates, constraints, mode, provenance, public_profiles in order:
            sources = ["qloo", "gemini"]
            if chooser.randrange(2):
                sources.reverse()
            options = {}
            for label, source in zip(("A", "B"), sources):
                proposal = decisions[source]["proposal"]
                options[label] = {key: proposal[key] for key in ("status", "selection", "schedule", "cost_units", "duration_minutes", "moves", "cycles", "unmatched", "reason") if key in proposal}
            pack.append({"case_id": case["id"], "category": case["category"], "prompt": case.get("prompt", "Which valid decision better serves these declared cultural references?"),
                         "candidates": candidates, "constraints": constraints, "evidence_mode": mode, "inventory_provenance": provenance,
                         "options": options, "preference": None, "reason": "", "profiles": public_profiles})
            mapping.append({"reviewer": reviewer, "case_id": case["id"], "A": sources[0], "B": sources[1]})
        write_json(output / (reviewer + ".json"), pack)
    write_json(output / "private-mapping.json", mapping)
    with (output / "responses-template.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["reviewer", "case_id", "preference", "reason"])
        for value in mapping:
            writer.writerow([value["reviewer"], value["case_id"], "", ""])
    return {"cases": 10, "reviewers": 5, "expected_judgments": 50, "seed": seed}


def score_reviews(pack_path, responses_path):
    mapping = {(value["reviewer"], value["case_id"]): value for value in read_json(Path(pack_path) / "private-mapping.json")}
    seen = set()
    totals = {"qloo": 0, "gemini": 0, "tie": 0, "neither": 0}
    reasons = []
    with Path(responses_path).open(newline="", encoding="utf-8") as handle:
        for response in csv.DictReader(handle):
            if not response.get("preference", "").strip():
                continue
            key = (response["reviewer"], response["case_id"])
            require(key in mapping and key not in seen, "Unknown or repeated reviewer/case response.")
            seen.add(key)
            preference = response["preference"].strip()
            require(preference in ("A", "B", "tie", "neither"), "Preference must be A, B, tie, or neither.")
            require(bool(response.get("reason", "").strip()), "Record a reason for every judgment.")
            winner = mapping[key][preference] if preference in ("A", "B") else preference
            totals[winner] += 1
            reasons.append(dict(response, decoded_preference=winner))
    return {"status": "complete" if len(seen) == len(mapping) else "partial", "received": len(seen), "expected": len(mapping),
            "totals": totals, "judgments": reasons, "note": "Five reviewers are not fifty independent participants. No statistical superiority claim is made."}
