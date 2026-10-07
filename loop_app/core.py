import copy
import json
import os
import secrets
import threading
import uuid
from pathlib import Path

from shootout.clients import Qloo, Transport, entity_id, parse_qloo_ranking, result_entities
from shootout.fixture import identifier, require, validate_fixture
from shootout.metrics import ranks, utilities
from shootout.solver import solve_loop, trade_signature, validate_exchange
from shootout.storage import ExperimentError, digest, read_json, redact, utcnow
from .store import DocumentStore, SavedEvidence

DATA = Path(__file__).parent / "data"
VARIANTS = {"music_only": "Music", "music_movies": "Music + films", "music_brands": "Music + brands"}


def ranking_key(candidates, references, source="qloo"):
    return digest({"source": source, "pool": [x["qloo_id"].lower() for x in candidates],
                   "references": sorted(x["qloo_id"].lower() for x in references)})


class Workspace:
    def __init__(self, directory, transport=None, qloo=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.busy = False
        self.secrets = tuple(filter(None, [os.getenv("QLOO_API_KEY"), os.getenv("GEMINI_API_KEY"), os.getenv("LOOP_ADMIN_PASSWORD"), os.getenv("LOOP_DATABASE_URL")]))
        self.store = DocumentStore(self.directory)
        self.transport = transport or Transport(SavedEvidence(self.directory / "evidence", self.store, self.secrets),
                                               max_requests=120, timeout=40, intervals={"qloo": 0.22, "gemini": 12})
        self.qloo = qloo or (Qloo(self.transport) if os.getenv("QLOO_API_KEY") else None)
        self.catalog = read_json(DATA / "demo.json")
        self.capture = read_json(DATA / "rankings.json")
        self.cache = {}
        refs = {x["id"]: x for x in self.catalog["references"]}
        for row in self.capture["rows"]:
            selected = [refs[x] for x in row["reference_ids"]]
            self.cache[ranking_key(self.catalog["candidates"], selected, row["source"])] = dict(
                row, captured_at=self.capture["captured_at"], provenance="saved_api_response",
                candidate_qloo={c["id"]: c["qloo_id"].lower() for c in self.catalog["candidates"]})
        self.cache.update(self.store.read("live-rankings.json", {}))
        self.known_references = {x["qloo_id"].lower(): x for x in self.catalog["references"]}
        for book in self.catalog["candidates"]:
            self.remember_book(book)
        saved = self.store.read("state.json")
        if saved:
            self.state = saved
            validate_fixture(self.state["fixture"])
            for values in self.state["taste"].values():
                self.known_references.update({x["qloo_id"].lower(): x for x in values})
            for book in self.state["fixture"]["candidates"]:
                self.remember_book(book)
        else:
            self.state = self.fresh_state()
            self.plan(self.state, lambda *args: None)
        self.save()

    def remap_ranking(self, row, candidates):
        result = copy.deepcopy(row)
        original = row.get("candidate_qloo", {c["id"]: c["qloo_id"].lower() for c in self.catalog["candidates"]})
        current = {c["qloo_id"].lower(): c["id"] for c in candidates}
        mapping = {cid: current[qid] for cid, qid in original.items() if qid in current}
        result["groups"] = [[mapping[cid] for cid in group if cid in mapping] for group in row["groups"]]
        result["groups"] = [group for group in result["groups"] if group]
        result["raw_scores"] = {mapping[cid]: value for cid, value in row.get("raw_scores", {}).items() if cid in mapping}
        result["pool_ids"] = [c["id"] for c in candidates]
        result["candidate_qloo"] = {c["id"]: c["qloo_id"].lower() for c in candidates}
        return result

    def remember_book(self, book):
        qid = book["qloo_id"].lower()
        self.known_references[qid] = {"id": "ref-" + qid[:18], "qloo_id": qid, "name": book["name"],
            "type": "book", "author": book.get("author", ""), "disambiguation": book.get("author", ""), "confirmed": True}

    def scenario(self, state=None):
        fixture = (state or self.state)["fixture"]
        return "Fictional owners and offers; genuine Qloo cultural rankings." if fixture["provenance"] == "synthetic_test" else "Owner-declared inventory and public references; Qloo cultural rankings."

    def fresh_state(self):
        fixture = copy.deepcopy(self.catalog)
        refs = {x["id"]: x for x in fixture["references"]}
        taste = {p["id"]: [refs[x] for x in next(g for g in fixture["profiles"] if g["id"] == p["profile_id"])["variants"]["music_only"]]
                 for p in fixture["participants"]}
        return {"fixture": fixture, "taste": taste, "variant": "music_only", "revision": 0,
                "proposal": None, "previous": None, "approvals": {}, "ranking_info": {}, "matrix": {}, "pool": [],
                "timeline": [], "messages": [{"role": "assistant", "engine": "workspace",
                    "text": "Four readers. Sixteen books. A new chapter for everyone. Find a loop, explore someone's taste, or withdraw a book to see the exchange adapt."}]}

    def save(self):
        self.store.write_many({"state.json": redact(self.state, self.secrets),
            "circles/" + self.state["fixture"]["id"] + ".json": redact(self.state, self.secrets), "proposal.json": self.export()})

    def export(self):
        return {"product": "Loop", "circle": self.state["fixture"].get("name", "Demo reading circle"), "scenario": self.scenario(),
                "revision": self.state["revision"], "generated_at": utcnow(), "proposal_id": self.state.get("proposal_id"),
                "proposal": self.state["proposal"], "approvals": self.state["approvals"], "participants": self.state["fixture"]["participants"],
                "copies": self.state["fixture"]["candidates"],
                "ranking_evidence": self.state["ranking_info"], "input_hash": digest({"fixture": self.state["fixture"], "taste": self.state["taste"]})}

    def public(self):
        with self.lock:
            result = copy.deepcopy(self.state)
            result.update(busy=self.busy, capabilities={"live_qloo": self.qloo is not None,
                "gemini": bool(os.getenv("GEMINI_API_KEY")), "model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")},
                captured_at=max((r.get("captured_at", self.capture["captured_at"]) for r in self.state["ranking_info"].values()), default=self.capture["captured_at"]))
            result["baseline"] = {}
            for person in result["fixture"]["participants"]:
                values = self.cache.get(ranking_key(result["fixture"]["candidates"], result["taste"][person["id"]], "gemini"))
                if values and result["fixture"]["provenance"] == "synthetic_test":
                    result["baseline"][person["id"]] = {"ranks": ranks(values["groups"], result["pool"]), "model": values.get("model")}
            return redact(result, self.secrets)

    def plan(self, draft, emit, refresh=False):
        fixture = draft["fixture"]
        for pid, approval in draft.get("approvals", {}).items():
            if approval.get("accepted") is False:
                incoming = next((m["candidate_id"] for m in draft["proposal"].get("moves", []) if m["to"] == pid), None)
                person = next(p for p in fixture["participants"] if p["id"] == pid)
                if incoming:
                    permitted = person.get("acceptable_ids", [c["id"] for c in fixture["candidates"]])
                    person["acceptable_ids"] = [cid for cid in permitted if cid != incoming]
                    emit("record_preference", "Exclude the declined incoming book for " + person["name"] + ".")
        validate_fixture(fixture)
        emit("read_workspace", "Read the offered copies and each reader's restrictions.")
        info = {}
        pool = set(x["id"] for x in fixture["candidates"])
        for person in fixture["participants"]:
            pid = person["id"]
            references = draft["taste"][pid]
            key = ranking_key(fixture["candidates"], references)
            cached = self.cache.get(key)
            if refresh or cached is None:
                require(self.qloo is not None, "Live Qloo access is needed for these references. Select a demo profile or configure QLOO_API_KEY on the server.")
                emit("qloo_rank", "Ask Qloo to rank the same %d books for %s." % (len(fixture["candidates"]), person["name"]))
                payload, evidence_id, _ = self.qloo.rank(fixture["candidates"], references, "loop")
                parsed = parse_qloo_ranking(payload, fixture["candidates"])
                require(len(ranks(parsed["groups"])) >= 8, "Qloo ranked fewer than eight books. The previous proposal has been preserved.")
                cached = dict(parsed, source="qloo", captured_at=utcnow(), provenance="live_api_response", evidence_id=evidence_id,
                    candidate_qloo={c["id"]: c["qloo_id"].lower() for c in fixture["candidates"]})
                self.cache[key] = cached
                self.store.write("live-rankings.json", {k: v for k, v in self.cache.items() if v.get("provenance") == "live_api_response"})
            else:
                emit("qloo_rank", "Use the saved Qloo ordering for " + person["name"] + ".")
            cached = self.remap_ranking(cached, fixture["candidates"])
            pool &= set(ranks(cached["groups"]))
            info[pid] = copy.deepcopy(cached)
        require(len(pool) >= 8, "Fewer than eight common books are ranked. The previous proposal has been preserved.")
        matrix = {person["profile_id"]: utilities(info[person["id"]]["groups"], pool)
                  for person in fixture["participants"]}
        emit("solve_exchange", "Find the best closed exchanges that respect offers, language, reading history, and the taste floor.")
        proposal = solve_loop(fixture, matrix, pool)
        emit("validate_exchange", "Check every handoff against ownership and availability.")
        validation = validate_exchange(fixture, proposal, pool, matrix)
        require(validation["valid"], "An invalid proposal was rejected before applying it.")
        old = draft.get("proposal")
        draft["previous"] = copy.deepcopy(old)
        draft.update(proposal=proposal, matrix=matrix, ranking_info=info, pool=sorted(pool), validation=validation)
        draft["proposal_id"] = digest({"input": {"fixture": fixture, "taste": draft["taste"]}, "proposal": proposal})[:16]
        # A fresh review is necessary after any new proposal or changed cultural input.
        draft["approvals"] = {}
        old_moves = set(trade_signature(old.get("moves", []))) if old else set()
        new_moves = set(trade_signature(proposal.get("moves", [])))
        draft["changes"] = {"removed": [list(x) for x in sorted(old_moves - new_moves)],
                            "added": [list(x) for x in sorted(new_moves - old_moves)]}
        emit("apply_proposal", "Save the validated proposal. Readers still decide whether to accept.")
        return self.summary(draft)

    def summary(self, state=None):
        state = state or self.state
        names = {x["id"]: x["name"] for x in state["fixture"]["candidates"]}
        moves = [dict(x, book=names[x["candidate_id"]], qloo_rank=ranks(state["ranking_info"][x["to"]]["groups"], state["pool"])[x["candidate_id"]])
                 for x in state["proposal"].get("moves", [])]
        return {"status": state["proposal"]["status"], "proposal_id": state.get("proposal_id"), "moves": moves,
                "people_served": len(state["proposal"].get("fit", {})), "cycles": len(state["proposal"].get("cycles", [])),
                "changes": state.get("changes", {}), "constraints_valid": state.get("validation", {}).get("valid", False),
                "note": self.scenario(state) + " Relative rank fit does not measure a person's satisfaction."}

    def circles(self):
        with self.lock:
            result = []
            for name in self.store.names("circles/"):
                saved = self.store.read(name)
                fixture = saved["fixture"]
                result.append({"id": fixture["id"], "name": fixture.get("name", "Demo reading circle"),
                    "demo": fixture["provenance"] == "synthetic_test", "books": len(fixture["candidates"]),
                    "readers": len(fixture["participants"]), "active": fixture["id"] == self.state["fixture"]["id"]})
            return sorted(result, key=lambda x: (x["demo"], x["name"].lower()))

    def create_circle(self, draft, data, emit):
        name = data.get("name", "")
        require(isinstance(name, str) and 1 <= len(name.strip()) <= 60, "Name the reading circle (up to 60 characters).")
        participants = data.get("participants")
        copies = data.get("books")
        require(isinstance(participants, list) and len(participants) == 4, "Add four readers to this pilot circle.")
        require(isinstance(copies, list) and 8 <= len(copies) <= 20, "Add eight to twenty distinct book titles.")
        require(data.get("attested") is True, "Confirm that the references were chosen and the offered copies belong to these readers.")
        fixture = copy.deepcopy(self.catalog)
        fixture.update(id="circle-" + uuid.uuid4().hex[:16], name=name.strip(), provenance="participant_inventory", inventory_attested=True,
                       note="Owner-declared inventory. Public entity matches selected by the user. Preference quality remains unmeasured.")
        refs = {r["qloo_id"].lower(): copy.deepcopy(r) for r in fixture["references"]}
        taste = {}
        colors = [p["color"] for p in fixture["participants"]]
        readers = []
        for i, incoming in enumerate(participants):
            require(isinstance(incoming, dict), "Invalid reader details.")
            alias = incoming.get("name", "")
            require(isinstance(alias, str) and 1 <= len(alias.strip()) <= 40, "Give each reader a name or nickname (up to 40 characters).")
            selected = incoming.get("references", [])
            require(isinstance(selected, list) and 1 <= len(selected) <= 8, "Each reader needs one to eight public cultural references.")
            selected_ids = [str(r.get("qloo_id", "")).lower() for r in selected if isinstance(r, dict)]
            require(len(selected_ids) == len(selected) == len(set(selected_ids)) and all(qid in self.known_references for qid in selected_ids),
                    "Select distinct confirmed cultural matches for every reader.")
            pid = "P%d" % (i + 1)
            for qid in selected_ids:
                if qid not in refs:
                    reference = copy.deepcopy(self.known_references[qid])
                    reference["id"] = "ref-" + qid[:18]
                    refs[qid] = reference
            taste[pid] = [copy.deepcopy(refs[qid]) for qid in selected_ids]
            languages = incoming.get("languages", ["en"])
            require(isinstance(languages, list) and set(languages) <= {"en", "fr", "hi", "es"}, "Choose supported reading languages.")
            initials = "".join(word[0] for word in alias.split()[:2]).upper() or "R"
            readers.append({"id": pid, "profile_id": fixture["profiles"][i]["id"], "name": alias.strip(), "initials": initials,
                "color": colors[i], "bio": "A new story starts with what you love.", "languages": languages,
                "references_attested": True, "human_ranking": [], "ranking_recorded_at": None, "already_read_ids": []})
            fixture["profiles"][i]["variants"]["declared"] = [r["id"] for r in taste[pid]]
        candidates = []
        resolved = set()
        for i, incoming in enumerate(copies):
            require(isinstance(incoming, dict), "Invalid offered copy.")
            qid = str(incoming.get("qloo_id", "")).lower()
            match = self.known_references.get(qid)
            require(match is not None and match["type"] == "book" and qid not in resolved, "Select distinct confirmed book works from search.")
            require(incoming.get("owner") in {p["id"] for p in readers}, "Assign every copy to its reader.")
            language = incoming.get("language", "en")
            require(language in {"en", "fr", "hi", "es"}, "Choose the copy's reading language.")
            author = incoming.get("author", match.get("author", ""))
            require(isinstance(author, str) and 1 <= len(author.strip()) <= 160, "Add the author to confirm the intended book.")
            candidates.append({"id": "copy-" + qid.replace("-", "")[:16], "name": match["name"], "type": "book", "qloo_id": qid,
                "confirmed": True, "author": author.strip(), "owner": incoming["owner"], "language": language,
                "offered": True, "available": True})
            resolved.add(qid)
        require({c["owner"] for c in candidates} == {p["id"] for p in readers}, "Each reader needs at least one offered copy.")
        fixture.update(candidates=candidates, references=list(refs.values()), participants=readers)
        fixture.pop("frozen_hash", None)
        validate_fixture(fixture)
        revision = draft["revision"]
        draft.clear()
        draft.update(fixture=fixture, taste=taste, variant="declared", revision=revision, proposal=None, previous=None,
            approvals={}, ranking_info={}, matrix={}, pool=[], timeline=[], messages=[{"role": "assistant", "engine": "workspace",
                "text": "Welcome to %s. Your offered copies and chosen references are ready. Let's find an exchange everyone can review." % name.strip()}])
        emit("create_circle", "Create the reading circle from owner-declared books and selected references.")

    def explain(self, state=None):
        state = state or self.state
        p = state["proposal"]
        if p["status"] == "no_exchange":
            return "There is no closed exchange under the current offers, language restrictions, reading history, and taste floor. Restore a copy or adjust a restriction, then try again. Nobody's books have moved."
        candidates = {x["id"]: x for x in state["fixture"]["candidates"]}
        people = {x["id"]: x for x in state["fixture"]["participants"]}
        lines = ["Found an exchange for %d readers across %d loop%s." % (len(p["fit"]), len(p["cycles"]), "s" if len(p["cycles"]) != 1 else "")]
        for move in p["moves"]:
            receiver = people[move["to"]]
            rank = ranks(state["ranking_info"][receiver["id"]]["groups"], state["pool"])[move["candidate_id"]]
            lines.append("%s receives %s from %s (Qloo rank %g of %d)." %
                         (receiver["name"], candidates[move["candidate_id"]]["name"], people[move["from"]]["name"], rank, len(state["pool"])))
        lines.append("All handoffs satisfy the current restrictions. Everyone involved must accept before exchanging physical copies.")
        return "\n\n".join(lines)

    def action(self, draft, action, data, emit):
        require(action in {"plan", "withdraw", "restore", "variant", "profile", "constraints", "refresh", "reset", "explain", "create_circle", "update_circle", "open_circle"}, "Unknown workspace action.")
        fixture = draft["fixture"]
        if action == "explain":
            return self.summary(draft)
        if action == "open_circle":
            cid = data.get("circle_id")
            require(identifier(cid), "Choose a saved reading circle.")
            saved = self.circle_state(cid)
            validate_fixture(saved["fixture"])
            validation = validate_exchange(saved["fixture"], saved["proposal"], saved["pool"], saved["matrix"])
            require(validation["valid"], "The saved proposal no longer meets its restrictions.")
            saved["revision"] = draft["revision"]
            draft.clear()
            draft.update(saved)
            for values in draft["taste"].values():
                self.known_references.update({r["qloo_id"].lower(): r for r in values})
            for book in draft["fixture"]["candidates"]:
                self.remember_book(book)
            emit("open_circle", "Open the saved circle and its current proposal.")
            return self.summary(draft)
        if action in {"create_circle", "update_circle"}:
            old = copy.deepcopy(draft)
            if action == "update_circle":
                require(data.get("circle_id") == fixture["id"] and fixture["provenance"] != "synthetic_test", "Open your circle before editing it.")
            self.create_circle(draft, data, emit)
            if action == "update_circle":
                draft["fixture"]["id"] = old["fixture"]["id"]
                draft["fixture"]["constraints"] = old["fixture"]["constraints"]
                draft["proposal"] = old["proposal"]
                draft["timeline"] = old["timeline"]
                allowed = {c["id"] for c in draft["fixture"]["candidates"]}
                for person in draft["fixture"]["participants"]:
                    before = next(p for p in old["fixture"]["participants"] if p["id"] == person["id"])
                    person["already_read_ids"] = [cid for cid in before.get("already_read_ids", []) if cid in allowed]
                    rejected = {c["id"] for c in old["fixture"]["candidates"] if "acceptable_ids" in before and c["id"] not in before["acceptable_ids"]}
                    if old["approvals"].get(person["id"], {}).get("accepted") is False:
                        rejected.update(m["candidate_id"] for m in old["proposal"].get("moves", []) if m["to"] == person["id"])
                    person["acceptable_ids"] = sorted(allowed - rejected)
                old_available = {c["id"]: c["available"] for c in old["fixture"]["candidates"]}
                for candidate in draft["fixture"]["candidates"]:
                    candidate["available"] = old_available.get(candidate["id"], True)
                emit("update_circle", "Save the edited shelf and readers, retaining reading restrictions and withdrawn copies.")
            return self.plan(draft, emit)
        if action in {"withdraw", "restore"}:
            book = next((x for x in fixture["candidates"] if x["id"] == data.get("copy_id")), None)
            require(book is not None, "Choose a copy from the shared shelf.")
            book["available"] = action == "restore"
            emit(action + "_copy", ("Restore " if action == "restore" else "Withdraw ") + book["name"] + ".")
        elif action == "variant":
            require(fixture["provenance"] == "synthetic_test", "Demo lenses apply to the example circle. Edit individual readers' own references here.")
            variant = data.get("variant")
            require(variant in VARIANTS, "Choose a supported taste lens.")
            refs = {x["id"]: x for x in self.catalog["references"]}
            for p in fixture["participants"]:
                profile = next(x for x in self.catalog["profiles"] if x["id"] == p["profile_id"])
                draft["taste"][p["id"]] = [refs[x] for x in profile["variants"][variant]]
            draft["variant"] = variant
            emit("update_taste", "Switch all demo readers to " + VARIANTS[variant] + " references.")
        elif action == "profile":
            pid = data.get("participant_id")
            person = next((x for x in fixture["participants"] if x["id"] == pid), None)
            require(person is not None, "Choose a reader.")
            references = data.get("references")
            require(isinstance(references, list) and 1 <= len(references) <= 8, "Choose one to eight confirmed cultural references.")
            selected = []
            for reference in references:
                qid = str(reference.get("qloo_id", "")).lower()
                require(qid in self.known_references, "Choose a confirmed search result or a demo reference.")
                selected.append(copy.deepcopy(self.known_references[qid]))
            require(len({x["qloo_id"].lower() for x in selected}) == len(selected), "Use distinct taste references.")
            draft["taste"][pid] = selected
            draft["variant"] = "custom"
            if "languages" in data:
                require(isinstance(data["languages"], list) and set(data["languages"]) <= {"en", "fr", "hi", "es"}, "Unsupported reading language.")
                person["languages"] = data["languages"]
            if "already_read_ids" in data:
                read_ids = data["already_read_ids"]
                require(isinstance(read_ids, list) and set(read_ids) <= {x["id"] for x in fixture["candidates"]}, "Choose read books from this shelf.")
                person["already_read_ids"] = list(set(read_ids))
            if "declined_ids" in data:
                declined = data["declined_ids"]
                require(isinstance(declined, list) and set(declined) <= {x["id"] for x in fixture["candidates"]}, "Choose declined titles from this shelf.")
                person["acceptable_ids"] = [x["id"] for x in fixture["candidates"] if x["id"] not in declined]
                draft["approvals"].pop(pid, None)
            emit("update_taste", "Update " + person["name"] + "'s references and restrictions.")
        elif action == "constraints":
            floor = data.get("fit_floor")
            require(isinstance(floor, (int, float)) and not isinstance(floor, bool) and 0 <= floor <= 1, "Taste floor must be between zero and one.")
            fixture["constraints"]["fit_floor"] = floor
            emit("update_constraints", "Apply the new minimum relative rank fit.")
        elif action == "reset":
            reset = self.fresh_state()
            reset["revision"] = draft["revision"]
            draft.clear()
            draft.update(reset)
            emit("reset_workspace", "Restore the original fictional shelf and taste profiles.")
        return self.plan(draft, emit, refresh=action == "refresh")

    def commit(self, draft, message, engine, trace, expected):
        with self.lock:
            require(self.state["revision"] == expected, "The workspace changed. Reload before applying this proposal.")
            draft["revision"] = expected + 1
            draft["messages"] = (draft["messages"] + [{"role": "assistant", "text": message, "engine": engine, "trace": trace}])[-24:]
            draft["timeline"] = (draft["timeline"] + [{"revision": draft["revision"], "at": utcnow(), "steps": trace,
                                                      "status": draft["proposal"]["status"]}])[-20:]
            before = self.state
            self.state = draft
            try:
                self.save()
            except Exception:
                self.state = before
                raise

    def accept(self, pid, accepted, proposal_id, circle_id=None, source="organizer"):
        with self.lock:
            require(not self.busy, "Wait for the current plan to finish.")
            state = self.circle_state(circle_id) if circle_id else copy.deepcopy(self.state)
            require(proposal_id == state.get("proposal_id"), "This proposal was replaced. Review the current incoming book before accepting.")
            require(pid in state["proposal"].get("fit", {}), "This reader has no handoff in the proposal.")
            require(isinstance(accepted, bool), "Acceptance must be true or false.")
            state["approvals"][pid] = {"accepted": accepted, "at": utcnow(), "proposal_id": proposal_id,
                "source": source, "simulated": state["fixture"]["provenance"] == "synthetic_test"}
            state["revision"] += 1
            self.save_circle(state)

    def circle_state(self, cid):
        require(identifier(cid), "Choose a saved reading circle.")
        saved = copy.deepcopy(self.state) if cid == self.state["fixture"]["id"] else self.store.read("circles/" + cid + ".json")
        require(saved is not None, "This circle is no longer available.")
        for values in saved["taste"].values():
            self.known_references.update({r["qloo_id"].lower(): r for r in values})
        for book in saved["fixture"]["candidates"]:
            self.remember_book(book)
        return saved

    def save_circle(self, state):
        if state["fixture"]["id"] == self.state["fixture"]["id"]:
            before = self.state
            self.state = state
            try:
                self.save()
            except Exception:
                self.state = before
                raise
        else:
            self.store.write("circles/" + state["fixture"]["id"] + ".json", redact(state, self.secrets))

    def commit_reader(self, draft, expected, trace):
        with self.lock:
            require(self.circle_state(draft["fixture"]["id"])["revision"] == expected, "The circle changed. Review the new proposal.")
            draft["revision"] = expected + 1
            draft["timeline"] = (draft["timeline"] + [{"revision": draft["revision"], "at": utcnow(), "steps": trace, "status": draft["proposal"]["status"]}])[-20:]
            draft["messages"] = (draft["messages"] + [{"role": "assistant", "text": self.explain(draft), "engine": "reader tools", "trace": trace}])[-24:]
            self.save_circle(draft)

    def invites(self, rotate=False):
        with self.lock:
            cid = self.state["fixture"]["id"]
            all_links = self.store.read("invites.json", {})
            links = all_links.setdefault(cid, {})
            for person in self.state["fixture"]["participants"]:
                pid = person["id"]
                if rotate or pid not in links:
                    links[pid] = {"token": secrets.token_urlsafe(32), "issued_at": utcnow(), "joined_at": None}
            self.store.write("invites.json", all_links)
            return {"circle": self.state["fixture"].get("name", "Demo reading circle"), "readers": [dict(links[p["id"]],
                name=p["name"], id=p["id"], approval=self.state["approvals"].get(p["id"])) for p in self.state["fixture"]["participants"]]}

    def reader_identity(self, token):
        require(isinstance(token, str) and len(token) == 43, "This reader link is invalid or was replaced. Ask your organizer for a new link.")
        links = self.store.read("invites.json", {})
        for cid, readers in links.items():
            for pid, entry in readers.items():
                if secrets.compare_digest(token, entry["token"]):
                    if not entry.get("joined_at"):
                        entry["joined_at"] = utcnow()
                        self.store.write("invites.json", links)
                    return cid, pid
        raise ExperimentError("This reader link is invalid or was replaced. Ask your organizer for a new link.")

    def reader_view(self, token):
        with self.lock:
            cid, pid = self.reader_identity(token)
            state = self.circle_state(cid)
            fixture = state["fixture"]
            people = {p["id"]: p for p in fixture["participants"]}
            person = people[pid]
            books = {c["id"]: c for c in fixture["candidates"]}
            moves = state["proposal"].get("moves", [])
            incoming = next((m for m in moves if m["to"] == pid), None)
            outgoing = next((m for m in moves if m["from"] == pid), None)
            approved = state["approvals"]
            involved = set(state["proposal"].get("fit", {}))
            ready = bool(involved) and all(approved.get(p, {}).get("accepted") is True for p in involved)
            def handoff(move, neighbor):
                return {"book": books[move["candidate_id"]], "reader": people[move[neighbor]]["name"]} if move else None
            rank = ranks(state["ranking_info"].get(pid, {}).get("groups", []), state["pool"]).get(incoming["candidate_id"]) if incoming else None
            # Other readers' profiles, inventory, chat, and individual votes stay in the organizer workspace.
            return redact({"circle_id": cid, "circle": fixture.get("name", "Demo reading circle"), "revision": state["revision"],
                "proposal_id": state["proposal_id"], "demo": fixture["provenance"] == "synthetic_test", "busy": self.busy,
                "person": {k: person.get(k) for k in ("id", "name", "initials", "color", "languages")},
                "references": state["taste"][pid], "offered": [c for c in books.values() if c["owner"] == pid],
                "incoming": handoff(incoming, "from"), "outgoing": handoff(outgoing, "to"), "rank": rank, "pool_size": len(state["pool"]),
                "approval": approved.get(pid), "ready": ready, "accepted_count": sum(approved.get(p, {}).get("accepted") is True for p in involved),
                "involved_count": len(involved), "status": state["proposal"]["status"], "feedback": state.get("reader_feedback", {}).get(pid),
                "live_qloo": self.qloo is not None}, self.secrets)

    def backup(self):
        with self.lock:
            # Private reader links are regenerated after restore and never included in downloadable evidence.
            return {"product": "Loop", "version": 1, "generated_at": utcnow(),
                "circles": [self.store.read(name) for name in self.store.names("circles/")],
                "live_rankings": self.store.read("live-rankings.json", {}),
                "evidence": [json.loads(line) for line in self.transport.evidence.path.read_text(encoding="utf-8").splitlines()] if self.transport.evidence.path.exists() else []}

    def search(self, query, kind):
        require(kind in {"artist", "movie", "brand", "book"}, "Choose artist, movie, brand, or book.")
        require(isinstance(query, str) and 2 <= len(query.strip()) <= 100 and "@" not in query and "://" not in query,
                "Search for a public cultural title, artist, or brand.")
        query = query.strip()
        matches = [x for x in self.known_references.values() if x["type"] == kind and query.lower() in x["name"].lower()]
        if matches:
            return {"results": matches[:5], "source": "confirmed_demo_entities"}
        require(self.qloo is not None, "Configure QLOO_API_KEY to search beyond the demo references.")
        with self.lock:
            require(not self.busy, "Wait for the current plan to finish before searching.")
            payload, evidence_id, _ = self.qloo.search({"name": query, "type": kind})
            options = []
            for item in result_entities(payload):
                qid = entity_id(item)
                uuid.UUID(qid)
                option = {"qloo_id": qid, "name": item["name"], "type": kind,
                          "disambiguation": item.get("disambiguation", ""), "confirmed": True}
                options.append(option)
                self.known_references[qid] = option
            return {"results": options, "source": "live_qloo_search", "evidence_id": evidence_id}
