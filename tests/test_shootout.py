import copy
import csv
import io
import json
import random
import tempfile
import unittest
from itertools import combinations, permutations, product
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from shootout.__main__ import init_loop, preflight
from shootout.clients import ApiError, Gemini, NoRedirect, Qloo, Transport, gemini_prompt, parse_gemini_ranking, parse_qloo_ranking
from shootout.demo import demo_fixture, run_demo
from shootout.evaluation import review_pack, score_reviews
from shootout.experiment import analyze, execute_rankings, resolve_fixture, select_project
from shootout.fixture import validate_fixture, variant_rows
from shootout.metrics import matched_agreement, ranks, spearman, utilities
from shootout.report import write_report
from shootout.solver import solve_loop, solve_understudy, validate_exchange, validate_program
from shootout.storage import Evidence, ExperimentError, fixture_hash, read_json, workspace_lock


class FakeResponse:
    status = 200
    headers = {"X-RateLimit-Remaining": "17", "x-api-key": "never-record-this-header"}

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.payload


class FakeOpener:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.requests = []

    def open(self, request, **kwargs):
        self.requests.append(request)
        if self.error:
            raise self.error
        return FakeResponse(self.payload)


def recordings(fixture, mode="synthetic"):
    ids = [candidate["id"] for candidate in fixture["candidates"]]
    rows = []
    for index, (profile, variant, reference_ids) in enumerate(variant_rows(fixture)):
        for source in ("qloo", "gemini"):
            offset = (index * 3) % len(ids) if source == "qloo" else 0
            order = ids[offset:] + ids[:offset]
            rows.append({"source": source, "profile_id": profile["id"], "variant": variant, "reference_ids": reference_ids,
                         "pool_ids": ids, "groups": [[value] for value in order], "status": "ok"})
    return {"mode": mode, "started_at": "2026-10-07T10:00:00+00:00", "fixture_hash": fixture["frozen_hash"], "rows": rows}


class MetricTests(unittest.TestCase):
    def test_midrank_and_ordinal_normalization(self):
        groups = [["a"], ["b", "c"], ["d"]]
        self.assertEqual(ranks(groups), {"a": 1, "b": 2.5, "c": 2.5, "d": 4})
        self.assertEqual(utilities(groups, {"a", "b", "c", "d"}), {"a": 1, "b": 0.5, "c": 0.5, "d": 0})
        self.assertAlmostEqual(utilities(groups, {"a", "b", "c", "d"}, "reciprocal")["b"], 0.4)

    def test_spearman_contrasting_order_and_ties(self):
        order = [[str(value)] for value in range(10)]
        self.assertAlmostEqual(spearman(order, list(reversed(order)), set(map(str, range(10))))["rho"], -1)
        tied = [[str(value) for value in range(3)]] + order[3:]
        self.assertIsNone(spearman(tied, order, set(map(str, range(10)))))

    def test_pairwise_sources_use_identical_untied_pairs(self):
        result = matched_agreement([["a", "b"], ["c"]], [["c"], ["b"], ["a"]], ["a", "b", "c"])
        self.assertEqual(result, {"qloo": 1, "gemini": 0, "compared": 2})

    def test_missing_candidates_cannot_receive_invented_utility(self):
        with self.assertRaises(ExperimentError):
            utilities([["a"], ["b"]], {"a", "b", "c"})


class ClientTests(unittest.TestCase):
    def test_book_author_disambiguation_survives_without_automatic_confirmation(self):
        fixture = demo_fixture("loop")
        fixture.pop("frozen_hash")
        candidate = fixture["candidates"][0]
        candidate.pop("qloo_id")
        candidate["confirmed"] = False
        matches = [{"entity_id": "00000000-0000-0000-0000-000000000001", "name": "Frankenstein",
                    "types": ["urn:entity:book"], "disambiguation": "2006, Deanna McFadden"},
                   {"entity_id": "00000000-0000-0000-0000-000000000002", "name": "Frankenstein: The 1818 Text",
                    "types": ["urn:entity:book"], "disambiguation": "1818, Mary Wollstonecraft Shelley"}]
        with tempfile.TemporaryDirectory() as directory:
            opener = FakeOpener({"results": matches})
            qloo = Qloo(Transport(Evidence(Path(directory) / "evidence"), opener=opener), key="test-only")
            result = resolve_fixture(fixture, qloo, Path(directory) / "choices.json")
            options = result["resolution_options"][candidate["id"]]["options"]
            self.assertEqual(options[0]["disambiguation"], "2006, Deanna McFadden")
            self.assertEqual(options[1]["disambiguation"], "1818, Mary Wollstonecraft Shelley")
            self.assertFalse(result["candidates"][0]["confirmed"])
            self.assertNotIn("qloo_id", result["candidates"][0])
            self.assertEqual(len(opener.requests), 1)

    def test_echoed_credentials_redacted_and_budget_failure_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = "test-secret-not-real-credential"
            opener = FakeOpener({"results": [], "echo": secret})
            evidence = Evidence(directory)
            transport = Transport(evidence, max_requests=1, opener=opener)
            transport.request("qloo", "GET", "https://hackathon.api.qloo.com/search", {"x-api-key": secret})
            with self.assertRaises(ApiError):
                transport.request("qloo", "GET", "https://hackathon.api.qloo.com/search", {"x-api-key": secret})
            saved = (Path(directory) / "requests.jsonl").read_text()
            self.assertNotIn(secret, saved)
            self.assertNotIn("never-record-this-header", saved)
            records = [json.loads(line) for line in saved.splitlines()]
            self.assertEqual(records[-1]["status"], "not_sent")
            self.assertEqual(len(opener.requests), 1)

    def test_http_quota_failure_captured_without_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            error = HTTPError("https://hackathon.api.qloo.com/search", 429, "Quota", {"Retry-After": "60"}, io.BytesIO(b'{"error":"quota"}'))
            opener = FakeOpener(error=error)
            transport = Transport(Evidence(directory), opener=opener)
            with self.assertRaises(ApiError) as caught:
                transport.request("qloo", "GET", "https://hackathon.api.qloo.com/search", {"x-api-key": "test-only"})
            self.assertEqual(caught.exception.status, 429)
            self.assertEqual(len(opener.requests), 1)
            record = json.loads((Path(directory) / "requests.jsonl").read_text())
            self.assertEqual(record["response_headers"]["Retry-After"], "60")

    def test_credentials_never_sent_to_another_host(self):
        with tempfile.TemporaryDirectory() as directory:
            opener = FakeOpener({})
            transport = Transport(Evidence(directory), opener=opener)
            with self.assertRaises(ExperimentError):
                transport.request("qloo", "GET", "https://example.org/search", {"x-api-key": "test-only"})
            self.assertEqual(opener.requests, [])
            self.assertIsNone(NoRedirect().redirect_request(None, None, 302, None, None, "https://example.org"))

    def test_qloo_shortlist_and_ties(self):
        candidates = [{"id": "a", "qloo_id": "id-a"}, {"id": "b", "qloo_id": "id-b"}]
        payload = {"results": {"entities": [{"entity_id": "ID-A", "query": {"affinity": 0.9}}, {"entity_id": "ID-B", "query": {"affinity": 0.9}}]}}
        self.assertEqual(parse_qloo_ranking(payload, candidates)["groups"], [["a", "b"]])
        payload["results"]["entities"][1]["entity_id"] = "outside-shortlist"
        with self.assertRaises(ExperimentError):
            parse_qloo_ranking(payload, candidates)

    def test_qloo_empty_and_out_of_order_do_not_fabricate_a_ranking(self):
        candidates = [{"id": "a", "qloo_id": "id-a"}, {"id": "b", "qloo_id": "id-b"}]
        empty = parse_qloo_ranking({"results": {"entities": []}}, candidates)
        self.assertEqual(empty["groups"], [])
        self.assertEqual(empty["missing"], ["a", "b"])
        entities = [{"entity_id": "id-a", "query": {"affinity": 0.5}}, {"entity_id": "id-b", "query": {"affinity": 0.9}}]
        with self.assertRaises(ExperimentError):
            parse_qloo_ranking({"results": {"entities": entities}}, candidates)

    def test_pacing_honors_the_configured_provider_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            opener = FakeOpener({"results": []})
            transport = Transport(Evidence(directory), opener=opener, intervals={"qloo": 15})
            with patch("shootout.clients.time.monotonic", return_value=100), patch("shootout.clients.time.sleep") as sleep:
                for _ in range(2):
                    transport.request("qloo", "GET", "https://hackathon.api.qloo.com/search", {"x-api-key": "test-only"})
                sleep.assert_called_once_with(15)

    def test_gemini_complete_permutation_and_private_input_exclusion(self):
        candidate = {"id": "a", "name": "Public Book", "type": "book", "owner": "PRIVATE_OWNER", "human_ranking": ["secret"], "fee_units": 55}
        prompt = gemini_prompt([candidate], [{"name": "Public Film", "type": "movie", "email": "private@example.org"}])
        self.assertNotIn("PRIVATE_OWNER", prompt)
        self.assertNotIn("private@example.org", prompt)
        self.assertNotIn("human_ranking", prompt)
        payload = {"status": "completed", "model": "test-model", "steps": [{"type": "model_output", "content": [{"type": "text", "text": '{"groups":[["a"]]}'}]}]}
        self.assertEqual(parse_gemini_ranking(payload, [candidate])["groups"], [["a"]])
        with self.assertRaises(ExperimentError):
            parse_gemini_ranking(payload, [candidate, dict(candidate, id="b")])

    def test_preflight_without_keys_makes_no_access_claim(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {}, clear=True):
            result = preflight(directory, 2)
            self.assertEqual(result["access"]["qloo"]["status"], "pending")
            self.assertEqual(result["quota"], "unverified")
            self.assertFalse((Path(directory) / "requests.jsonl").exists())


class UnderstudyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = demo_fixture("understudy")
        self.fixture["candidates"] = self.fixture["candidates"][1:5]
        self.fixture["constraints"].update(budget_units=70, original_ids=[], fit_floor=0.5)
        for index, candidate in enumerate(self.fixture["candidates"]):
            candidate["fee_units"] = 40 if index < 2 else 30
        self.pool = {candidate["id"] for candidate in self.fixture["candidates"]}
        a, b, c, d = [candidate["id"] for candidate in self.fixture["candidates"]]
        self.matrix = {profile["id"]: ({a: 1, b: 0.1, c: 0.9, d: 0.1} if index % 2 == 0 else {a: 0.1, b: 1, c: 0.1, d: 0.2})
                       for index, profile in enumerate(self.fixture["profiles"])}

    def test_complementary_program_and_regret_ignore_other_cohort_floors(self):
        proposal = solve_understudy(self.fixture, self.matrix, self.pool)
        self.assertEqual(set(proposal["selection"]), {"act-03", "act-04"})
        self.assertEqual(proposal["cost_units"], 70)
        self.assertAlmostEqual(proposal["regret"]["profile-alt"], 0.1)
        self.assertEqual(proposal["individual_ideal"]["profile-alt"], 1)
        self.assertTrue(validate_program(self.fixture, proposal, self.pool, self.matrix)["valid"])

    def test_order_sensitive_availability_and_changes(self):
        self.fixture["constraints"]["budget_units"] = 80
        self.fixture["candidates"][0].update(available_from=45, available_until=80)
        self.fixture["candidates"][1].update(available_from=0, available_until=35)
        proposal = solve_understudy(self.fixture, self.matrix, self.pool)
        self.assertEqual(proposal["selection"], ["act-03", "act-02"])
        self.assertEqual(proposal["schedule"][1]["start_minute"], 45)

    def test_expired_original_and_equipment_constraints(self):
        self.fixture["constraints"].update(original_ids=["act-02"], budget_units=100)
        self.fixture["candidates"][1]["offer_expires_at"] = "2020-01-01T00:00:00+00:00"
        self.fixture["candidates"][2]["equipment"] = ["unavailable-console"]
        result = solve_understudy(self.fixture, self.matrix, self.pool)
        self.assertEqual(result["status"], "infeasible")
        self.assertEqual(result["selection"], [])

    def test_validator_rejects_a_fabricated_schedule(self):
        proposal = solve_understudy(self.fixture, self.matrix, self.pool)
        proposal["cost_units"] = 1
        self.assertFalse(validate_program(self.fixture, proposal, self.pool, self.matrix)["valid"])


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.fixture = demo_fixture("loop")
        self.fixture["candidates"] = [self.fixture["candidates"][index] for index in (0, 4, 8, 12)]
        self.fixture["constraints"]["fit_floor"] = 0.5
        self.pool = {candidate["id"] for candidate in self.fixture["candidates"]}
        self.matrix = {profile["id"]: {candidate["id"]: 0 for candidate in self.fixture["candidates"]} for profile in self.fixture["profiles"]}
        for profile, cid in zip(self.fixture["profiles"][:3], ("book-05", "book-09", "book-01")):
            self.matrix[profile["id"]][cid] = 1

    def test_three_way_trade_exists_without_a_direct_swap(self):
        result = solve_loop(self.fixture, self.matrix, self.pool)
        self.assertEqual(len(result["moves"]), 3)
        self.assertEqual(result["unmatched"], ["P4"])
        self.assertEqual(len(result["cycles"][0]), 3)
        self.assertTrue(validate_exchange(self.fixture, result, self.pool, self.matrix)["valid"])

    def test_withdrawal_removes_the_entire_broken_cycle(self):
        result = solve_loop(self.fixture, self.matrix, self.pool, withdrawn=["book-05"])
        self.assertEqual(result["status"], "no_exchange")
        self.assertEqual(result["moves"], [])
        self.assertTrue(validate_exchange(self.fixture, result, self.pool, self.matrix, withdrawn=["book-05"])["valid"])

    def test_language_read_history_and_explicit_empty_acceptability(self):
        for restriction in ({"languages": ["fr"]}, {"already_read_ids": ["book-05"]}, {"acceptable_ids": []}):
            fixture = copy.deepcopy(self.fixture)
            fixture["participants"][0].update(restriction)
            self.assertEqual(solve_loop(fixture, self.matrix, self.pool)["status"], "no_exchange")

    def test_validator_catches_wrong_owner_and_open_chains(self):
        result = solve_loop(self.fixture, self.matrix, self.pool)
        result["moves"][0]["from"] = "P4"
        self.assertFalse(validate_exchange(self.fixture, result, self.pool, self.matrix)["valid"])

    def test_exact_solver_matches_independent_exhaustive_assignments(self):
        chooser = random.Random(91)
        for trial in range(25):
            fixture = demo_fixture("loop")
            fixture["candidates"] = [item for index, item in enumerate(fixture["candidates"]) if index % 4 < 2]
            fixture["constraints"]["fit_floor"] = 0.4
            pool = {item["id"] for item in fixture["candidates"]}
            matrix = {profile["id"]: {item["id"]: chooser.randrange(6) / 5 for item in fixture["candidates"]} for profile in fixture["profiles"]}
            people = fixture["participants"]
            options = [[None] + [item for item in fixture["candidates"] if item["owner"] == person["id"]] for person in people]
            optimal = (0, 0, 0)
            for offered in product(*options):
                selected = [(person, item) for person, item in zip(people, offered) if item is not None]
                if len(selected) < 2:
                    continue
                for receivers in permutations([person for person, _ in selected]):
                    if any(sender["id"] == receiver["id"] for (sender, _), receiver in zip(selected, receivers)):
                        continue
                    scores = [matrix[receiver["profile_id"]][item["id"]] for (_, item), receiver in zip(selected, receivers)]
                    if min(scores) >= 0.4:
                        optimal = max(optimal, (len(scores), min(scores), sum(scores)))
            actual = solve_loop(fixture, matrix, pool)
            value = (len(actual.get("fit", {})), actual.get("worst_fit", 0), actual.get("total_fit", 0))
            self.assertEqual(value[:2], optimal[:2], "trial %d" % trial)
            self.assertAlmostEqual(value[2], optimal[2], msg="trial %d" % trial)


class EvidenceGateTests(unittest.TestCase):
    def test_synthetic_success_can_never_select_a_product(self):
        fixture = demo_fixture("understudy")
        report = analyze(fixture, recordings(fixture))
        self.assertEqual(report["selection"], "pending")
        self.assertTrue(all(gate["status"] == "pending" for gate in report["gates"].values()))

    def test_unmeasured_resolution_and_missing_keys_remain_pending(self):
        fixture = demo_fixture("understudy")
        for item in fixture["candidates"] + fixture["references"]:
            item.pop("qloo_id")
            item.pop("confirmed")
        fixture["frozen_hash"] = fixture_hash(fixture)
        with tempfile.TemporaryDirectory() as directory:
            data = execute_rankings(fixture, {}, Path(directory) / "run")
            report = analyze(fixture, data)
            self.assertEqual(report["selection"], "pending")
            self.assertEqual(report["gates"]["candidate_resolution"]["status"], "pending")

    def test_all_tied_results_do_not_pass_contrasting_profiles(self):
        fixture = demo_fixture("understudy")
        data = recordings(fixture, mode="live")
        for row in data["rows"]:
            row["groups"] = [row["pool_ids"]]
        report = analyze(fixture, data)
        self.assertEqual(report["gates"]["contrasting_profiles"]["status"], "fail")

    def test_common_pool_coverage_cannot_be_inflated_by_missing_rows(self):
        fixture = demo_fixture("understudy")
        data = recordings(fixture, mode="live")
        data["rows"].pop()
        report = analyze(fixture, data)
        self.assertEqual(report["common_pool"], [])
        self.assertEqual(report["gates"]["common_pool"]["status"], "pending")

    def test_successful_empty_qloo_results_fail_coverage(self):
        fixture = demo_fixture("understudy")
        data = recordings(fixture, mode="live")
        for row in data["rows"]:
            if row["source"] == "qloo":
                row["groups"] = []
        report = analyze(fixture, data)
        self.assertEqual(report["gates"]["common_pool"]["status"], "fail")
        self.assertEqual(report["selection"], "no_go")

    def test_changed_fixture_or_foreign_evidence_is_rejected(self):
        fixture = demo_fixture("understudy")
        data = recordings(fixture)
        fixture["constraints"]["budget_units"] += 1
        with self.assertRaises(ExperimentError):
            analyze(fixture, data)
        fixture["frozen_hash"] = fixture_hash(fixture)
        with self.assertRaises(ExperimentError):
            analyze(fixture, data)

    def test_hindsight_and_missing_acceptance_cannot_pass_loop(self):
        fixture = demo_fixture("loop")
        fixture.update(provenance="participant_inventory", inventory_attested=True)
        for participant in fixture["participants"]:
            participant.update(references_attested=True, human_ranking=[item["id"] for item in fixture["candidates"]], ranking_recorded_at="2026-10-08T10:00:00+00:00")
        fixture["frozen_hash"] = fixture_hash(fixture)
        report = analyze(fixture, recordings(fixture, mode="live"))
        self.assertEqual(report["gates"]["human_preference_advantage"]["status"], "pending")
        self.assertNotEqual(report["gates"]["accepted_multilateral_exchange"]["status"], "pass")

    def test_complete_human_grounded_pilot_can_pass_and_baseline_wins_can_fail(self):
        fixture = demo_fixture("loop")
        fixture.update(provenance="participant_inventory", inventory_attested=True)
        ids = [candidate["id"] for candidate in fixture["candidates"]]
        orders = {}
        for index, participant in enumerate(fixture["participants"]):
            shift = ((index + 1) % 4) * 4
            order = ids[shift:] + ids[:shift]
            orders[participant["profile_id"]] = order
            participant.update(references_attested=True, human_ranking=order, ranking_recorded_at="2026-10-07T08:00:00+00:00")
        fixture["frozen_hash"] = fixture_hash(fixture)
        data = recordings(fixture, mode="live")
        for row in data["rows"]:
            if row["variant"] == "declared":
                order = orders[row["profile_id"]]
                row["groups"] = [[value] for value in (order if row["source"] == "qloo" else list(reversed(order)))]
        first_report = analyze(fixture, data)
        declared = next(value for value in first_report["decisions"] if value["source"] == "qloo" and value["variant"] == "declared" and value["utility"] == "ordinal")
        feedback = {"loop_acceptance": {declared["proposal_id"]: {"recorded_at": "2026-10-07T11:00:00+00:00",
                    "participants": {person["id"]: {"accepted": True, "reason": "Accept this proposed incoming book."} for person in fixture["participants"]}}}}
        report = analyze(fixture, data, feedback)
        self.assertEqual(report["selection"], "eligible")
        self.assertEqual(report["gates"]["human_preference_advantage"]["detail"]["participant_wins"], 4)
        self.assertTrue(report["gates"]["withdrawal_repair"]["detail"]["validation"]["valid"])
        for person in fixture["participants"]:
            person["human_ranking"] = list(reversed(person["human_ranking"]))
        fixture["frozen_hash"] = fixture_hash(fixture)
        data["fixture_hash"] = fixture["frozen_hash"]
        baseline_report = analyze(fixture, data)
        self.assertEqual(baseline_report["gates"]["human_preference_advantage"]["status"], "fail")
        self.assertTrue(all(value["gemini"] > value["qloo"] for value in baseline_report["human_results"]))

    def test_duplicate_qloo_works_and_domain_mismatch_rejected(self):
        fixture = demo_fixture("loop")
        fixture["candidates"][1]["qloo_id"] = fixture["candidates"][0]["qloo_id"]
        with self.assertRaises(ExperimentError):
            validate_fixture(fixture)
        fixture = demo_fixture("understudy")
        fixture["profiles"][0]["variants"]["music_only"].append("alt-movie-1")
        with self.assertRaises(ExperimentError):
            validate_fixture(fixture)

    def test_project_selection_prioritizes_only_eligible_results(self):
        self.assertEqual(select_project([{"kind": "loop", "selection": "eligible"}, {"kind": "understudy", "selection": "eligible"}])["decision"], "loop")
        self.assertEqual(select_project([{"kind": "loop", "selection": "no_go"}, {"kind": "understudy", "selection": "no_go"}])["decision"], "reopen_ideation")
        self.assertEqual(select_project([{"kind": "understudy", "selection": "pending"}])["decision"], "pending")

    def test_workspace_prevents_simultaneous_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            with workspace_lock(directory):
                with self.assertRaises(ExperimentError):
                    with workspace_lock(directory):
                        pass
            self.assertFalse((Path(directory) / ".shootout.lock").exists())


class ArtifactAndReviewTests(unittest.TestCase):
    def test_live_report_qualifies_baseline_model_and_synthetic_operating_inputs(self):
        fixture = demo_fixture("loop")
        evidence = recordings(fixture, mode="live")
        for row in evidence["rows"]:
            if row["source"] == "gemini":
                row["model"] = "gemini-3.5-flash-lite"
                row["groups"] = [sum(row["groups"][:3], [])] + row["groups"][3:]
        report = analyze(fixture, evidence)
        with tempfile.TemporaryDirectory() as directory:
            write_report(fixture, evidence, report, directory)
            document = (Path(directory) / "report.html").read_text()
            top = document[:document.index("<h2>Gates")]
            self.assertIn("Gemini baseline: gemini-3.5-flash-lite", top)
            self.assertIn("SYNTHETIC OPERATIONAL INPUTS", top)
            for candidate in fixture["candidates"][:3]:
                self.assertIn(candidate["name"] + " (rank 2)", document)
        self.assertEqual(report["gates"]["real_inventory"]["status"], "pending")

    def test_partial_live_report_shows_captured_rankings_without_passing_comparison(self):
        fixture = demo_fixture("understudy")
        fixture["candidates"][0]["name"] = "<Wolf & Alice>"
        fixture["frozen_hash"] = fixture_hash(fixture)
        evidence = recordings(fixture, mode="live")
        for row in evidence["rows"]:
            if row["source"] == "gemini":
                row.update(status="pending", groups=[], reason="Credential not configured.")
        report = analyze(fixture, evidence)
        self.assertEqual(report["mechanism"], "pending")
        self.assertEqual(report["selection"], "pending")
        with tempfile.TemporaryDirectory() as directory:
            write_report(fixture, evidence, report, directory)
            document = (Path(directory) / "report.html").read_text()
            self.assertIn("LIVE EVIDENCE INCOMPLETE", document)
            self.assertIn("SYNTHETIC OPERATIONAL INPUTS", document)
            self.assertIn("Captured ranking previews", document)
            self.assertIn("&lt;Wolf &amp; Alice&gt;", document)
            self.assertNotIn("<Wolf & Alice>", document)
            self.assertTrue((Path(directory) / "comparison.png").exists())

    def test_report_png_and_blinded_reviews_preserve_baseline_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_demo(root / "demo")
            run = root / "demo" / "understudy"
            self.assertEqual((run / "comparison.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            html = (run / "report.html").read_text()
            self.assertIn("SYNTHETIC VERIFICATION", html)
            manifest = read_json(Path(__file__).resolve().parent.parent / "evaluation" / "cases-template.json")
            for case in manifest["cases"]:
                case["report_path"] = "demo/understudy"
            (root / "cases.json").write_text(json.dumps(manifest))
            review_pack(root / "cases.json", root / "pack", seed=41)
            pack = read_json(root / "pack" / "reviewer-1.json")
            self.assertEqual(len(pack), 10)
            self.assertEqual(set(pack[0]["options"]), {"A", "B"})
            self.assertNotIn("worst_fit", json.dumps(pack))
            self.assertTrue(pack[0]["profiles"][0]["references"])
            mapping = read_json(root / "pack" / "private-mapping.json")
            entry = mapping[0]
            label = "A" if entry["A"] == "gemini" else "B"
            with (root / "responses.csv").open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["reviewer", "case_id", "preference", "reason"])
                writer.writerow([entry["reviewer"], entry["case_id"], label, "Fits these declared interests better."])
            result = score_reviews(root / "pack", root / "responses.csv")
            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["totals"]["gemini"], 1)
            self.assertEqual(result["expected"], 50)

    def test_actual_inventory_initialization_does_not_attest_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = demo_fixture("loop")
            inventory = Path(directory) / "books.csv"
            fields = ["id", "name", "author", "owner", "language", "available", "offered"]
            with inventory.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for item in fixture["candidates"]:
                    writer.writerow({key: str(item[key]).lower() if isinstance(item[key], bool) else item[key] for key in fields})
            output = Path(directory) / "loop.json"
            init_loop(inventory, output)
            self.assertFalse(read_json(output)["inventory_attested"])
            self.assertEqual(len(read_json(output)["candidates"]), 16)


if __name__ == "__main__":
    unittest.main()
