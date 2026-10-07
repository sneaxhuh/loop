import copy
import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from loop_app.agent import Agent
from loop_app.core import Workspace
from loop_app.__main__ import LoopServer
from shootout.solver import trade_signature, validate_exchange
from shootout.storage import ExperimentError, read_json


class FakeQloo:
    def __init__(self, count=16):
        self.calls = []
        self.count = count

    def rank(self, candidates, references, kind):
        self.calls.append(copy.deepcopy((candidates, references, kind)))
        return {"results": {"entities": [{"entity_id": c["qloo_id"], "query": {"affinity": 1-i/20}}
                for i, c in enumerate(candidates[:self.count])]}}, "test-evidence", {}


class FakeTransport:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, source, method, url, headers, body):
        self.calls.append(copy.deepcopy(body))
        return next(self.responses), "test-model-evidence", {}


class WorkspaceCase(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.temp = tempfile.TemporaryDirectory()
        self.ws = Workspace(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()
        self.environment.stop()

    def action(self, name, **data):
        draft = copy.deepcopy(self.ws.state)
        trace = []
        self.ws.action(draft, name, data, lambda tool, message: trace.append({"tool": tool, "message": message}))
        self.ws.commit(draft, self.ws.explain(draft), "test", trace, self.ws.state["revision"])
        self.assertTrue(validate_exchange(draft["fixture"], draft["proposal"], draft["pool"], draft["matrix"])["valid"])
        return trace

class WorkspaceTests(WorkspaceCase):
    def test_saved_real_rankings_produce_valid_four_reader_cycle_without_keys(self):
        self.assertEqual(len(self.ws.state["proposal"]["cycles"][0]), 4)
        self.assertEqual(len(self.ws.state["pool"]), 16)
        self.assertFalse(self.ws.public()["capabilities"]["live_qloo"])
        self.assertTrue(all(r["provenance"] == "saved_api_response" for r in self.ws.state["ranking_info"].values()))
        self.assertTrue(self.ws.state["validation"]["valid"])

    def test_withdrawal_repairs_and_restore_returns_original_decision(self):
        initial = trade_signature(self.ws.state["proposal"]["moves"])
        cid = self.ws.state["proposal"]["moves"][0]["candidate_id"]
        trace = self.action("withdraw", copy_id=cid)
        self.assertNotIn(cid, [m["candidate_id"] for m in self.ws.state["proposal"]["moves"]])
        self.assertTrue(self.ws.state["changes"]["removed"])
        self.assertIn("validate_exchange", [t["tool"] for t in trace])
        self.action("restore", copy_id=cid)
        self.assertEqual(initial, trade_signature(self.ws.state["proposal"]["moves"]))

    def test_cross_domain_lens_changes_actual_handoffs_using_cache(self):
        initial = trade_signature(self.ws.state["proposal"]["moves"])
        self.action("variant", variant="music_movies")
        self.assertNotEqual(initial, trade_signature(self.ws.state["proposal"]["moves"]))
        self.assertEqual(len(self.ws.public()["baseline"]), 4)
        self.assertTrue(any(r["type"] == "movie" for r in self.ws.state["taste"]["P1"]))

    def test_no_exchange_is_explicit_at_unachievable_floor(self):
        self.action("constraints", fit_floor=1)
        self.assertEqual(self.ws.state["proposal"]["status"], "no_exchange")
        self.assertEqual(self.ws.state["proposal"]["moves"], [])
        self.assertIn("no closed exchange", self.ws.explain())

    def test_language_and_read_history_are_hard_restrictions(self):
        self.action("profile", participant_id="P1", references=self.ws.state["taste"]["P1"], languages=["fr"], already_read_ids=[])
        self.assertNotIn("P1", self.ws.state["proposal"]["fit"])
        self.action("profile", participant_id="P1", references=self.ws.state["taste"]["P1"], languages=["en"],
                    already_read_ids=[c["id"] for c in self.ws.state["fixture"]["candidates"]])
        self.assertNotIn("P1", self.ws.state["proposal"]["fit"])

    def test_declined_title_is_excluded_on_replan_and_approvals_reset(self):
        move = self.ws.state["proposal"]["moves"][0]
        self.ws.accept(move["to"], False, self.ws.state["proposal_id"])
        self.action("plan")
        self.assertNotIn(move, self.ws.state["proposal"]["moves"])
        participant = next(p for p in self.ws.state["fixture"]["participants"] if p["id"] == move["to"])
        self.assertNotIn(move["candidate_id"], participant["acceptable_ids"])
        self.assertEqual(self.ws.state["approvals"], {})
        self.action("plan")
        self.assertNotIn(move, self.ws.state["proposal"]["moves"])

    def test_stale_acceptance_and_stale_commit_cannot_apply(self):
        old_id = self.ws.state["proposal_id"]
        stale = copy.deepcopy(self.ws.state)
        self.action("withdraw", copy_id=self.ws.state["proposal"]["moves"][0]["candidate_id"])
        with self.assertRaises(ExperimentError):
            self.ws.accept("P1", True, old_id)
        with self.assertRaises(ExperimentError):
            self.ws.commit(stale, "stale", "test", [], 0)

    def test_state_and_review_artifact_survive_restart(self):
        self.ws.accept("P1", True, self.ws.state["proposal_id"])
        restored = Workspace(self.temp.name)
        self.assertEqual(restored.state, self.ws.state)
        artifact = read_json(Path(self.temp.name) / "proposal.json")
        self.assertTrue(artifact["approvals"]["P1"]["simulated"])
        self.assertIn("Fictional", artifact["scenario"])
        self.assertEqual(artifact["proposal_id"], restored.state["proposal_id"])

    def test_failed_custom_taste_leaves_applied_workspace_unchanged(self):
        original = copy.deepcopy(self.ws.state)
        draft = copy.deepcopy(original)
        with self.assertRaises(ExperimentError):
            self.ws.action(draft, "profile", {"participant_id": "P1", "references": [{"qloo_id": "unconfirmed"}]}, lambda *args: None)
        self.assertEqual(self.ws.state, original)
        refs = [self.ws.catalog["references"][0]]
        with self.assertRaises(ExperimentError):
            self.ws.action(draft, "profile", {"participant_id": "P1", "references": refs}, lambda *args: None)
        self.assertEqual(self.ws.state, original)

    def test_live_ranking_uses_same_pool_and_public_refs_without_participant_data(self):
        self.ws.qloo = FakeQloo()
        self.action("profile", participant_id="P1", references=[self.ws.catalog["references"][0]])
        self.assertEqual(len(self.ws.qloo.calls), 1)
        candidates, references, kind = self.ws.qloo.calls[0]
        self.assertEqual(len(candidates), 16)
        self.assertEqual(kind, "loop")
        self.assertEqual(references[0]["type"], "artist")
        self.assertNotIn("human_ranking", references[0])
        self.assertEqual(self.ws.state["ranking_info"]["P1"]["provenance"], "live_api_response")
        self.action("plan")
        self.assertEqual(len(self.ws.qloo.calls), 1)

    def test_low_live_coverage_is_rejected(self):
        original = copy.deepcopy(self.ws.state)
        self.ws.qloo = FakeQloo(count=7)
        with self.assertRaises(ExperimentError):
            self.ws.action(copy.deepcopy(original), "profile", {"participant_id": "P1", "references": [self.ws.catalog["references"][0]]}, lambda *args: None)
        self.assertEqual(self.ws.state, original)

    def test_partial_live_coverage_uses_only_common_books_for_decisions_and_baseline(self):
        self.ws.qloo = FakeQloo(count=8)
        self.action("profile", participant_id="P1", references=[self.ws.catalog["references"][0]])
        self.assertEqual(len(self.ws.state["pool"]), 8)
        self.assertTrue(all(m["candidate_id"] in self.ws.state["pool"] for m in self.ws.state["proposal"]["moves"]))
        for baseline in self.ws.public()["baseline"].values():
            self.assertEqual(set(baseline["ranks"]), set(self.ws.state["pool"]))

    def test_guided_mode_changes_only_named_copy(self):
        agent = Agent(self.ws)
        draft = copy.deepcopy(self.ws.state)
        message, engine = agent.run("Withdraw Beloved", draft, lambda *args: None)
        self.assertEqual(engine, "guided")
        self.assertFalse(next(c for c in draft["fixture"]["candidates"] if c["name"] == "Beloved")["available"])
        self.assertIn("must accept", message)


class AgentProtocolTests(WorkspaceCase):
    # Keep protocol tests separate from the workspace cases.
    def test_native_function_result_replays_full_model_history(self):
        transport = FakeTransport([
            {"status": "requires_action", "steps": [{"type": "thought", "signature": "preserve-this"},
                {"type": "function_call", "name": "withdraw_copy", "id": "call-1", "arguments": {"copy_id": "book-03"}}]},
            {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": "The revised proposal is saved."}]}]},
        ])
        self.ws.transport = transport
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-only"}):
            agent = Agent(self.ws)
        draft = copy.deepcopy(self.ws.state)
        message, engine = agent.run("Please withdraw Beloved", draft, lambda *args: None)
        self.assertEqual(message, "The revised proposal is saved.")
        self.assertEqual(len(transport.calls), 2)
        history = transport.calls[1]["input"]
        self.assertEqual(history[1]["signature"], "preserve-this")
        self.assertEqual(history[-1]["call_id"], "call-1")
        result = json.loads(history[-1]["result"][0]["text"])
        self.assertNotIn("book-03", [m["candidate_id"] for m in result["moves"]])
        self.assertIn("qloo_rank", result["moves"][0])
        self.assertFalse(transport.calls[0]["store"])

    def test_model_cannot_change_availability_when_user_asks_for_explanation(self):
        self.ws.transport = FakeTransport([{ "status": "requires_action", "steps": [
            {"type": "function_call", "name": "withdraw_copy", "id": "call-1", "arguments": {"copy_id": "book-03"}}]}])
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-only"}):
            agent = Agent(self.ws)
        with self.assertRaises(ExperimentError):
            agent.run("Why is Beloved in the loop?", copy.deepcopy(self.ws.state), lambda *args: None)
        self.assertTrue(next(c for c in self.ws.state["fixture"]["candidates"] if c["id"] == "book-03")["available"])


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.temp = tempfile.TemporaryDirectory()
        self.server = LoopServer(("127.0.0.1", 0), Workspace(self.temp.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()
        self.environment.stop()

    def request(self, path, body=None, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Loop-Token"] = self.server.csrf
        request = Request(self.url + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_api_rejects_missing_token_and_data_files_are_not_public(self):
        with self.assertRaises(HTTPError) as denied:
            self.request("/api/agent", {"revision": 0, "action": "plan"}, token=False)
        self.assertEqual(denied.exception.code, 400)
        with self.assertRaises(HTTPError) as hidden:
            self.request("/data/rankings.json")
        self.assertEqual(hidden.exception.code, 404)

    def test_job_runs_validated_mutation_and_download_matches_current_proposal(self):
        current = self.request("/api/state")
        job = self.request("/api/agent", {"revision": current["revision"], "action": "withdraw", "copy_id": "book-03"})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.request("/api/jobs/" + job["job_id"])
            if result["status"] != "running":
                break
            time.sleep(0.02)
        self.assertEqual(result["status"], "complete")
        self.assertIn("apply_proposal", [t["tool"] for t in result["trace"]])
        current = self.request("/api/state")
        artifact = self.request("/api/export")
        self.assertEqual(current["proposal_id"], artifact["proposal_id"])
        self.assertNotIn("book-03", [m["candidate_id"] for m in artifact["proposal"]["moves"]])
        with self.assertRaises(HTTPError):
            self.request("/api/agent", {"revision": 0, "action": "reset"})


if __name__ == "__main__":
    unittest.main()
