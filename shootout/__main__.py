"""Run `python3 -m shootout --help`. No installation or credentials needed for demo."""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from .clients import ApiError, Gemini, Qloo, Transport
from .demo import run_demo
from .evaluation import review_pack, score_reviews
from .experiment import analyze, execute_rankings, resolve_fixture, select_project
from .fixture import confirmed, require, resolution_summary, validate_fixture
from .report import write_report
from .storage import Evidence, ExperimentError, fixture_hash, read_json, redact, utcnow, workspace_lock, write_json


def secrets():
    return [os.getenv("QLOO_API_KEY"), os.getenv("GEMINI_API_KEY")]


def emit(value):
    print(json.dumps(redact(value, secrets()), indent=2, ensure_ascii=False, allow_nan=False))


def make_transport(directory, budget, qloo_interval=0, gemini_interval=0):
    return Transport(Evidence(directory, secrets()), max_requests=budget, intervals={"qloo": qloo_interval, "gemini": gemini_interval})


def status():
    return {"qloo_key_present": bool(os.getenv("QLOO_API_KEY")), "gemini_key_present": bool(os.getenv("GEMINI_API_KEY")),
            "qloo_endpoint_valid": os.getenv("QLOO_BASE_URL", "https://hackathon.api.qloo.com").rstrip("/") == "https://hackathon.api.qloo.com"
                                   and os.getenv("QLOO_TRUSTED_BASE_URL", "https://hackathon.api.qloo.com").rstrip("/") == "https://hackathon.api.qloo.com",
            "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"), "quota": "unverified", "key_expiration": "unverified",
            "note": "Presence is not successful authentication. Use preflight for live read-only checks."}


def preflight(directory, budget):
    transport = make_transport(directory, budget)
    result = dict(status(), checked_at=utcnow(), access={})
    for provider in ("qloo", "gemini"):
        if not os.getenv("QLOO_API_KEY" if provider == "qloo" else "GEMINI_API_KEY"):
            result["access"][provider] = {"status": "pending", "reason": "Credential not configured."}
            continue
        try:
            if provider == "qloo":
                payload, evidence_id, headers = Qloo(transport).get("/search", {"query": "jazz", "types": "urn:entity:artist", "take": 1})
                detail = "Search access only; Insights and shortlist filtering must still be tested."
            else:
                payload, evidence_id, headers = transport.request("gemini", "GET", "https://generativelanguage.googleapis.com/v1beta/models",
                                                                  {"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
                names = [item.get("name", "") for item in payload.get("models", [])]
                detail = {"selected_model_listed": "models/" + result["gemini_model"] in names,
                          "note": "Model listing is not a generation test and does not establish free-tier entitlement."}
            result["access"][provider] = {"status": "ok", "evidence_id": evidence_id, "observed_limit_headers": headers, "detail": detail}
        except (ApiError, ExperimentError) as error:
            result["access"][provider] = {"status": "error", "reason": str(error), "evidence_id": getattr(error, "evidence_id", None)}
    write_json(Path(directory) / "preflight.json", redact(result, secrets()))
    return result


def confirm_matches(fixture, csv_path):
    validate_fixture(fixture)
    fixture.pop("frozen_hash", None)
    entities = {value["id"]: value for value in fixture["candidates"] + fixture["references"]}
    seen = set()
    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            require(row.get("id") in entities and row["id"] not in seen, "Unknown or repeated entity in confirmations CSV.")
            seen.add(row["id"])
            if row.get("qloo_id", "").strip():
                entities[row["id"]].update(qloo_id=row["qloo_id"].strip(), confirmed=True)
                entities[row["id"]].pop("resolution_status", None)
            elif row.get("unresolved", "").lower() == "true":
                entities[row["id"]].update(confirmed=False, resolution_status="unresolved")
                entities[row["id"]].pop("qloo_id", None)
    validate_fixture(fixture)
    return fixture


def collect_cards(fixture, output):
    validate_fixture(fixture)
    cards = {"fixture_id": fixture["id"], "instructions": "Rank all candidate ids by anticipated interest before seeing either system's output. Record a UTC timestamp. References must be public cultural entities, never personal identifiers.",
             "cards": [{key: value[key] for key in ("id", "name", "author", "neutral_description") if key in value} for value in fixture["candidates"]],
             "participants": [{"id": participant["id"], "human_ranking": [], "ranking_recorded_at": None,
                               "declared_references": [], "languages": participant.get("languages", [])} for participant in fixture.get("participants", [])]}
    write_json(output, cards)
    return {"cards": str(output), "candidates": len(cards["cards"]), "note": "Copy collected rankings and references into the fixture before freezing."}


def init_loop(inventory, output):
    fixture = read_json(Path(__file__).resolve().parent.parent / "fixtures" / "understudy.json")
    fixture.update(id="loop-shootout", kind="loop", provenance="participant_inventory", inventory_attested=False,
                   note="Inventory is user-supplied. Ownership/offers remain unverified until attested. Experimental profiles are synthetic probes; add real declared references separately.")
    candidates = []
    with Path(inventory).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            item = {key: row.get(key, "").strip() for key in ("id", "name", "author", "isbn", "owner", "language", "neutral_description")}
            item = {key: value for key, value in item.items() if value}
            for key in ("available", "offered"):
                require(row.get(key, "").strip().lower() in ("true", "false"), "Inventory CSV needs explicit true/false " + key)
                item[key] = row[key].strip().lower() == "true"
            item["type"] = "book"
            candidates.append(item)
    fixture["candidates"] = candidates
    fixture["constraints"] = {"fit_floor": 0.5, "max_cycle_length": 4}
    fixture["participants"] = [{"id": "P%d" % (index + 1), "profile_id": profile["id"], "languages": [], "references_attested": False,
                                "human_ranking": [], "ranking_recorded_at": None} for index, profile in enumerate(fixture["profiles"])]
    validate_fixture(fixture)
    write_json(output, fixture)
    return {"fixture": str(output), "candidates": len(candidates), "next": "Collect real references and independent rankings, attest ownership/offers, then resolve and freeze."}


def parser():
    result = argparse.ArgumentParser(description="Preregistered Qloo/Gemini evidence sprint. Synthetic demos never pass live gates.")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Check credential presence without printing keys or making requests.")
    check = commands.add_parser("preflight", help="Read-only access checks; unexposed quotas/expiration remain unknown.")
    check.add_argument("--out", required=True)
    check.add_argument("--max-requests", type=int, default=2)
    validate = commands.add_parser("validate", help="Validate a fixture and list unresolved candidates.")
    validate.add_argument("fixture")
    collect = commands.add_parser("collect", help="Create neutral, source-free participant ranking cards.")
    collect.add_argument("fixture")
    collect.add_argument("--out", required=True)
    initialize = commands.add_parser("init-loop", help="Create a Loop fixture from actual owned-book CSV; ownership stays unattested.")
    initialize.add_argument("--inventory", required=True)
    initialize.add_argument("--out", required=True)
    resolve = commands.add_parser("resolve", help="Save Qloo match choices; never select an ambiguous match automatically.")
    resolve.add_argument("fixture")
    resolve.add_argument("--out", required=True)
    resolve.add_argument("--evidence", required=True)
    resolve.add_argument("--max-requests", type=int, default=60)
    resolve.add_argument("--qloo-interval", type=float, default=0, help="Seconds between Qloo calls, based on your actual key's rate limit (0–60).")
    confirm = commands.add_parser("confirm", help="Import manually confirmed UUIDs or explicit unresolved decisions.")
    confirm.add_argument("fixture")
    confirm.add_argument("--csv", required=True)
    confirm.add_argument("--out", required=True)
    freeze = commands.add_parser("freeze", help="Freeze inventory, references, constraints, and pre-reveal human rankings.")
    freeze.add_argument("fixture")
    freeze.add_argument("--out", required=True)
    run = commands.add_parser("run", help="Request both rankings on one frozen pool and create the comparison report.")
    run.add_argument("fixture")
    run.add_argument("--out", required=True)
    run.add_argument("--max-requests", type=int, default=40)
    run.add_argument("--qloo-interval", type=float, default=0, help="Minimum seconds between Qloo requests (0–60).")
    run.add_argument("--gemini-interval", type=float, default=0, help="Minimum seconds between Gemini requests (0–60); set from actual free-tier limits.")
    analyze_command = commands.add_parser("analyze", help="Rebuild reports from captured evidence, optionally adding acceptance reviews.")
    analyze_command.add_argument("run")
    analyze_command.add_argument("--feedback")
    demo = commands.add_parser("demo", help="Exercise both solvers and report exports with hand-authored synthetic data.")
    demo.add_argument("--out", default="artifacts/synthetic-demo")
    decision = commands.add_parser("decision", help="Apply the preregistered project selection rule to saved reports.")
    decision.add_argument("reports", nargs="+")
    pack = commands.add_parser("review-pack", help="Create blinded ten-case packs for five reviewers.")
    pack.add_argument("manifest")
    pack.add_argument("--out", required=True)
    pack.add_argument("--seed", type=int, default=7)
    score = commands.add_parser("score-reviews", help="Decode blinded votes, retaining baseline wins, ties, neither, and reasons.")
    score.add_argument("pack")
    score.add_argument("responses")
    score.add_argument("--out", required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "status":
            emit(status())
        elif args.command == "preflight":
            with workspace_lock(Path.cwd()):
                emit(preflight(args.out, args.max_requests))
        elif args.command == "validate":
            fixture = validate_fixture(read_json(args.fixture))
            emit({"valid": True, "kind": fixture["kind"], "resolution": resolution_summary(fixture),
                  "unconfirmed_references": [value["id"] for value in fixture["references"] if not confirmed(value)]})
        elif args.command == "collect":
            emit(collect_cards(read_json(args.fixture), args.out))
        elif args.command == "init-loop":
            emit(init_loop(args.inventory, args.out))
        elif args.command == "resolve":
            with workspace_lock(Path.cwd()):
                output = resolve_fixture(read_json(args.fixture), Qloo(make_transport(args.evidence, args.max_requests, args.qloo_interval)), args.out)
                emit({"choices": args.out, "resolution": resolution_summary(output), "next": "Confirm correct identities manually using confirm or edit qloo_id and confirmed."})
        elif args.command == "confirm":
            output = confirm_matches(read_json(args.fixture), args.csv)
            write_json(args.out, output)
            emit({"fixture": args.out, "resolution": resolution_summary(output)})
        elif args.command == "freeze":
            fixture = validate_fixture(read_json(args.fixture))
            fixture["frozen_hash"] = fixture_hash(fixture)
            write_json(args.out, fixture)
            emit({"fixture": args.out, "frozen_hash": fixture["frozen_hash"]})
        elif args.command == "run":
            fixture = validate_fixture(read_json(args.fixture), frozen=True)
            # Check freshness before creating an evidence log in an existing directory.
            path = Path(args.out)
            require(not path.exists() or not any(path.iterdir()), "Use a fresh output directory.")
            with workspace_lock(Path.cwd()):
                transport = make_transport(path, args.max_requests, args.qloo_interval, args.gemini_interval)
                providers = {"qloo": Qloo(transport) if os.getenv("QLOO_API_KEY") else None,
                             "gemini": Gemini(transport) if os.getenv("GEMINI_API_KEY") else None}
                recordings = execute_rankings(fixture, providers, path)
                report = analyze(fixture, recordings)
                write_report(fixture, recordings, report, path)
                emit({"report": str(path / "report.html"), "snapshot": str(path / "comparison.png"),
                      "mechanism": report["mechanism"], "selection": report["selection"], "requests_sent": transport.attempts})
        elif args.command == "analyze":
            path = Path(args.run)
            fixture, recordings = read_json(path / "fixture.json"), read_json(path / "rankings.json")
            feedback = read_json(args.feedback) if args.feedback else None
            report = analyze(fixture, recordings, feedback)
            write_report(fixture, recordings, report, path)
            if feedback:
                write_json(path / "feedback.json", feedback)
            emit({"report": str(path / "report.html"), "mechanism": report["mechanism"], "selection": report["selection"]})
        elif args.command == "demo":
            with workspace_lock(Path.cwd()):
                emit(run_demo(args.out))
        elif args.command == "decision":
            emit(select_project([read_json(path) for path in args.reports]))
        elif args.command == "review-pack":
            emit(review_pack(args.manifest, args.out, args.seed))
        elif args.command == "score-reviews":
            result = score_reviews(args.pack, args.responses)
            write_json(args.out, result)
            emit(result)
        return 0
    except (ExperimentError, OSError, ValueError, KeyError, TypeError) as error:
        print(redact("Error: " + str(error), secrets()), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
