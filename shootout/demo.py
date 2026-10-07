"""Hand-authored synthetic rankings exercise code, never establish Qloo value."""

import copy
import uuid
from pathlib import Path

from .experiment import analyze
from .fixture import validate_fixture, variant_rows
from .report import write_report
from .storage import Evidence, fixture_hash, read_json, utcnow, write_json


def demo_fixture(kind):
    fixture = read_json(Path(__file__).resolve().parent.parent / "fixtures" / "understudy.json")
    fixture["id"] = "synthetic-" + kind
    fixture["kind"] = kind
    fixture["provenance"] = "synthetic_test"
    fixture["note"] = "Hand-authored synthetic %s fixture. UUIDs, ownership, availability, and rankings are test data; no empirical Qloo advantage is claimed." % kind
    fixture["constraints"]["fit_floor"] = 0.15
    if kind == "loop":
        books = [("Frankenstein", "Mary Shelley"), ("Dune", "Frank Herbert"), ("Beloved", "Toni Morrison"), ("The Left Hand of Darkness", "Ursula K. Le Guin"),
                 ("Pride and Prejudice", "Jane Austen"), ("The Hobbit", "J. R. R. Tolkien"), ("Never Let Me Go", "Kazuo Ishiguro"), ("The Stranger", "Albert Camus"),
                 ("The Great Gatsby", "F. Scott Fitzgerald"), ("The Handmaid's Tale", "Margaret Atwood"), ("The Name of the Rose", "Umberto Eco"), ("The Road", "Cormac McCarthy"),
                 ("Jane Eyre", "Charlotte Bronte"), ("The Dispossessed", "Ursula K. Le Guin"), ("The Secret History", "Donna Tartt"), ("The Remains of the Day", "Kazuo Ishiguro")]
        fixture["candidates"] = [{"id": "book-%02d" % (index + 1), "name": name, "author": author, "type": "book", "owner": "P%d" % (index // 4 + 1),
                                  "available": True, "offered": True, "language": "en"} for index, (name, author) in enumerate(books)]
        fixture["constraints"] = {"fit_floor": 0.15, "max_cycle_length": 4}
        fixture["participants"] = [{"id": "P%d" % (index + 1), "profile_id": profile["id"], "languages": ["en"], "references_attested": False,
                                    "human_ranking": [], "ranking_recorded_at": None} for index, profile in enumerate(fixture["profiles"])]
        for profile in fixture["profiles"]:
            profile["variants"]["declared"] = list(profile["variants"]["music_movies"])
    for entity in fixture["candidates"] + fixture["references"]:
        entity.update(qloo_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "synthetic-only:" + entity["id"])), confirmed=True)
    fixture["frozen_hash"] = fixture_hash(fixture)
    validate_fixture(fixture, frozen=True)
    return fixture


def run_demo(directory):
    root = Path(directory)
    if root.exists() and any(root.iterdir()):
        from .storage import ExperimentError
        raise ExperimentError("Use a fresh demo directory; previous evidence will not be overwritten.")
    outputs = []
    for kind in ("understudy", "loop"):
        path = root / kind
        fixture = demo_fixture(kind)
        ids = [candidate["id"] for candidate in fixture["candidates"]]
        evidence = Evidence(path)
        rows = []
        for profile, variant, reference_ids in variant_rows(fixture):
            index = next(index for index, value in enumerate(fixture["profiles"]) if value["id"] == profile["id"])
            shift = (index * 4 + (0 if variant == "music_only" else 2)) % len(ids)
            for source in ("qloo", "gemini"):
                offset = shift if source == "qloo" else (0 if variant == "music_only" else 1)
                order = ids[offset:] + ids[:offset]
                groups = [[value] for value in order]
                evidence_id = evidence.record({"mode": "synthetic", "provider": "hand_authored_test_fixture", "nominal_source": source,
                                                "profile_id": profile["id"], "variant": variant, "groups": groups})
                rows.append({"source": source, "profile_id": profile["id"], "variant": variant, "reference_ids": reference_ids,
                             "pool_ids": ids, "groups": groups, "status": "ok", "raw_scores": {}, "evidence_id": evidence_id})
        recordings = {"version": 1, "fixture_hash": fixture["frozen_hash"], "mode": "synthetic", "started_at": utcnow(), "rows": rows}
        report = analyze(fixture, recordings)
        write_json(path / "fixture.json", fixture)
        write_json(path / "rankings.json", recordings)
        write_report(fixture, recordings, report, path)
        outputs.append({"kind": kind, "report": str(path / "report.html"), "snapshot": str(path / "comparison.png"), "selection": report["selection"]})
    return outputs
