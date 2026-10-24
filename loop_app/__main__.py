"""Run with python3 -m loop_app. No installed packages are required."""
import argparse
import copy
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit

from shootout.fixture import require
from shootout.storage import ExperimentError, redact, utcnow, workspace_lock
from .agent import Agent
from .auth import OrganizerAuth
from .core import Workspace
from .store import DocumentStore
from shootout.fixture import identifier, validate_fixture
from shootout.solver import validate_exchange
from shootout.storage import read_json

STATIC = Path(__file__).parent / "static"


class LoopRuntime:
    def __init__(self, workspace, demo=False):
        self.workspace = workspace
        self.demo = demo
        self.agent = Agent(workspace)
        self.auth = OrganizerAuth("" if demo else os.getenv("LOOP_ADMIN_PASSWORD", ""))
        self.serverless = bool(os.getenv("VERCEL"))
        csrf_key = (os.getenv("LOOP_ADMIN_PASSWORD") or secrets.token_urlsafe(32)).encode()
        csrf_scope = ("loop-csrf:" + workspace.store.namespace).encode()
        self.csrf = hmac.new(hashlib.sha256(csrf_key).digest(), csrf_scope, hashlib.sha256).hexdigest()
        self.jobs = {}

    def save_job(self, job):
        self.jobs[job["id"]] = job
        if self.serverless and self.workspace.store.url:
            self.workspace.store.write("jobs/" + job["id"] + ".json", redact(job, self.workspace.secrets))

    def get_job(self, job_id):
        job = self.jobs.get(job_id)
        if job is None and self.serverless and self.workspace.store.url:
            job = self.workspace.store.read("jobs/" + job_id + ".json")
        return job

    def start_job(self, body):
        ws = self.workspace
        with ws.lock:
            require(not ws.busy, "A plan is already running. Wait for it to finish.")
            require(body.get("revision") == ws.state["revision"], "The workspace changed. Reload and try again.")
            text = body.get("message", "")
            action = body.get("action")
            require(action is not None or isinstance(text, str) and 1 <= len(text.strip()) <= 1200, "Write a short request for the agent.")
            expected = ws.state["revision"]
            draft = copy.deepcopy(ws.state)
            ws.busy = True
            job_id = secrets.token_hex(8)
            job = {"id": job_id, "status": "running", "trace": [], "started_at": utcnow()}
            self.save_job(job)
            if len(self.jobs) > 20:
                del self.jobs[next(iter(self.jobs))]

        def emit(tool, message):
            with ws.lock:
                job["trace"].append({"tool": tool, "message": message, "at": utcnow()})

        def work():
            try:
                if text:
                    draft["messages"].append({"role": "user", "text": redact(text, ws.secrets)})
                if action:
                    ws.action(draft, action, body, emit)
                    message, engine = ws.explain(draft), "workspace tools"
                else:
                    message, engine = self.agent.run(text, draft, emit)
                ws.commit(draft, redact(message, ws.secrets), engine, copy.deepcopy(job["trace"]), expected)
                with ws.lock:
                    job.update(status="complete", message=redact(message, ws.secrets), engine=engine)
            except (ExperimentError, ValueError, KeyError, TypeError) as error:
                with ws.lock:
                    job.update(status="error", error=redact(str(error), ws.secrets))
            except Exception:
                with ws.lock:
                    job.update(status="error", error="The request could not finish. The previous workspace was preserved.")
            finally:
                with ws.lock:
                    ws.busy = False
                    job["finished_at"] = utcnow()
                    self.save_job(job)
        if self.serverless:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()
        return {"job_id": job_id}

    def start_reader_job(self, body):
        ws = self.workspace
        with ws.lock:
            cid, pid = ws.reader_identity(body.get("token"))
            require(not ws.busy, "A plan is already running. Wait for it to finish.")
            draft = ws.circle_state(cid)
            require(body.get("revision") == draft["revision"] and body.get("proposal_id") == draft["proposal_id"], "The proposal changed. Review the current incoming book first.")
            action = body.get("action")
            require(action in {"decline", "withdraw", "restore", "profile"}, "Choose a reader action.")
            if action in {"withdraw", "restore"}:
                require(any(c["id"] == body.get("copy_id") and c["owner"] == pid for c in draft["fixture"]["candidates"]), "You can only change your own offered copies.")
            if action == "decline":
                require(pid in draft["proposal"].get("fit", {}), "There is no incoming book to pass on.")
            expected = draft["revision"]
            ws.busy = True
            job_id = secrets.token_hex(8)
            job = {"id": job_id, "status": "running", "trace": [], "started_at": utcnow()}
            self.save_job(dict(job, reader_key=body["token"]))
            job = self.jobs[job_id]
            if len(self.jobs) > 20:
                del self.jobs[next(iter(self.jobs))]

        def emit(tool, message):
            with ws.lock:
                # Reader progress shows tool names; other people's details stay private.
                job["trace"].append({"tool": tool, "message": tool.replace("_", " "), "at": utcnow()})

        def work():
            try:
                if action == "decline":
                    incoming = next(m["candidate_id"] for m in draft["proposal"]["moves"] if m["to"] == pid)
                    draft["approvals"][pid] = {"accepted": False, "proposal_id": draft["proposal_id"]}
                    draft.setdefault("reader_feedback", {})[pid] = {"action": "declined", "copy_id": incoming, "at": utcnow()}
                    ws.plan(draft, emit)
                elif action == "profile":
                    data = {"participant_id": pid, "references": body.get("references"), "languages": body.get("languages", [])}
                    ws.action(draft, action, data, emit)
                else:
                    ws.action(draft, action, {"copy_id": body.get("copy_id")}, emit)
                ws.commit_reader(draft, expected, copy.deepcopy(job["trace"]))
                with ws.lock:
                    job["status"] = "complete"
            except (ExperimentError, ValueError, KeyError, TypeError) as error:
                with ws.lock:
                    job.update(status="error", error=redact(str(error), ws.secrets))
            except Exception:
                with ws.lock:
                    job.update(status="error", error="The update could not finish. Your previous proposal was preserved.")
            finally:
                with ws.lock:
                    ws.busy = False
                    job["finished_at"] = utcnow()
                    self.save_job(job)
        if self.serverless:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()
        return {"job_id": job_id}


class LoopServer(ThreadingHTTPServer, LoopRuntime):
    daemon_threads = True

    def __init__(self, address, workspace):
        ThreadingHTTPServer.__init__(self, address, Handler)
        LoopRuntime.__init__(self, workspace)
        self.demo_lock = threading.RLock()
        self.demos = {}
        self.demo_signing_key = self.auth.key if self.auth.password else secrets.token_bytes(32)
        self.demo_starts = {}

    def demo_identity(self, cookie_header):
        try:
            cookie = SimpleCookie(cookie_header or "")
            value = cookie["loop_demo"].value
            identity, expires, signature = value.split(".")
            payload = identity + "." + expires
            expected = hmac.new(self.demo_signing_key, payload.encode(), hashlib.sha256).hexdigest()
            if len(identity) == 32 and all(c in "0123456789abcdef" for c in identity) and int(expires) > time.time() and hmac.compare_digest(signature, expected):
                return identity
        except (KeyError, ValueError, TypeError, CookieError):
            pass
        return None

    def demo_runtime(self, identity):
        with self.demo_lock:
            if identity not in self.demos:
                # Recreate the visitor's namespace after restarts without sharing
                # mutable workspace objects or changing process environment vars.
                directory = self.workspace.directory / "demos" / identity
                namespace = self.workspace.store.namespace + "-demo-" + identity
                ws = Workspace(directory, namespace=namespace)
                runtime = LoopRuntime(ws, demo=True)
                runtime.demo_identity = identity
                # Bound API usage per visitor while all saved-profile controls
                # continue to work without provider calls.
                ws.transport.max_requests = 24
                self.demos[identity] = runtime
                if len(self.demos) > 64:
                    for key, old in list(self.demos.items()):
                        if key != identity and not old.workspace.busy:
                            del self.demos[key]
                            break
            return self.demos[identity]

    def runtime_for(self, cookie_header, reader_token=None):
        if reader_token:
            marker = hashlib.sha256(reader_token.encode()).hexdigest()
            identity = self.workspace.store.read("demo-readers/" + marker + ".json")
            return self.demo_runtime(identity) if identity else self
        identity = self.demo_identity(cookie_header)
        if identity:
            return self.demo_runtime(identity)
        return self

    def start_demo(self, cookie_header, address):
        identity = self.demo_identity(cookie_header)
        if not identity:
            now = time.time()
            with self.demo_lock:
                self.demo_starts = {key: value for key, value in self.demo_starts.items() if now - value[0] < 3600}
                start, count = self.demo_starts.get(address, (now, 0))
                require(count < 12, "Several demo circles were opened recently. Please return to an existing demo or try again later.")
                self.demo_starts[address] = (start, count + 1)
            identity = secrets.token_hex(16)
        self.demo_runtime(identity)
        payload = identity + "." + str(int(time.time()) + 7 * 86400)
        signature = hmac.new(self.demo_signing_key, payload.encode(), hashlib.sha256).hexdigest()
        return payload + "." + signature


class Handler(BaseHTTPRequestHandler):
    server_version = "Loop/1.0"

    def log_message(self, fmt, *args):
        # Request bodies, prompts, credentials, and query strings are never logged.
        pass

    def send(self, status, data, kind="application/json", attachment=None, cookie=None):
        if kind == "application/json":
            data = json.dumps(redact(data, self.server.workspace.secrets), ensure_ascii=False, allow_nan=False).encode()
        elif isinstance(data, str):
            data = data.encode()
        self.send_response(status)
        self.send_header("Content-Type", kind + ("; charset=utf-8" if kind.startswith("text/") or kind == "application/json" else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if attachment:
            self.send_header("Content-Disposition", 'attachment; filename="' + attachment + '"')
        if cookie:
            for value in cookie if isinstance(cookie, list) else [cookie]:
                self.send_header("Set-Cookie", value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            self.root_server = self.server
            self.server = self.root_server.runtime_for(self.headers.get("Cookie"))
            self.server.workspace.refresh()
            authenticated = self.server.auth.authenticated(self.headers.get("Cookie"))
            if path.startswith("/api/") and not authenticated:
                return self.send(401, {"error": "Sign in to the organizer workspace."})
            if path == "/api/state":
                self.send(200, dict(self.server.workspace.public(), csrf_token=self.server.csrf, organizer_login=bool(self.server.auth.password) or self.server.demo, visitor_demo=self.server.demo))
            elif path == "/healthz":
                self.send(200, {"status": "ok", "service": "Loop"})
            elif path == "/api/circles":
                self.send(200, {"circles": self.server.workspace.circles()})
            elif path == "/api/export":
                with self.server.workspace.lock:
                    self.send(200, self.server.workspace.export(), attachment="loop-exchange.json")
            elif path == "/api/backup":
                self.send(200, self.server.workspace.backup(), attachment="loop-workspace-backup.json")
            elif path.startswith("/api/jobs/"):
                with self.server.workspace.lock:
                    job = self.server.get_job(path.rsplit("/", 1)[-1])
                    require(job is not None, "This agent run is no longer available.")
                    self.send(200, {k: v for k, v in job.items() if k != "reader_key"})
            elif path in {"/", "/join", "/app.js", "/circle.js", "/reader.js", "/login.js", "/style.css", "/circle.css", "/reader.css", "/favicon.svg"}:
                filename = ("index.html" if authenticated else "login.html") if path == "/" else "join.html" if path == "/join" else path[1:]
                self.send(200, (STATIC / filename).read_bytes(), mimetypes.guess_type(filename)[0] or "application/octet-stream")
            else:
                self.send(404, {"error": "Not found."})
        except ExperimentError as error:
            self.send(404, {"error": str(error)})

    def do_POST(self):
        try:
            self.root_server = self.server
            path = urlsplit(self.path).path
            reader_route = path.startswith("/api/reader/")
            origin = self.headers.get("Origin")
            require(not origin or urlsplit(origin).netloc == self.headers.get("Host"), "Cross-origin changes are not allowed.")
            require(self.headers.get("Content-Type", "").split(";")[0] == "application/json", "Use a JSON request.")
            length = int(self.headers.get("Content-Length", "0"))
            require(0 < length <= 24000, "Request is too large or empty.")
            body = json.loads(self.rfile.read(length))
            require(isinstance(body, dict), "Request must be a JSON object.")
            if path == "/api/demo":
                address = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
                session = self.root_server.start_demo(self.headers.get("Cookie"), address)
                secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                return self.send(200, {"status": "demo_ready"}, cookie="loop_demo=" + session + "; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800" + secure)
            self.server = self.root_server if path == "/api/login" else self.root_server.runtime_for(self.headers.get("Cookie"), body.get("token") if reader_route else None)
            self.server.workspace.refresh()
            if path != "/api/login" and not reader_route:
                if not self.server.auth.authenticated(self.headers.get("Cookie")):
                    return self.send(401, {"error": "Sign in to the organizer workspace."})
                require(secrets.compare_digest(self.headers.get("X-Loop-Token", ""), self.server.csrf), "Reload the page before making changes.")
            if path == "/api/login":
                with self.server.workspace.lock:
                    session, error = self.server.auth.login(body.get("password"), self.client_address[0])
                if error:
                    return self.send(403, {"error": error})
                secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                self.send(200, {"status": "signed_in"}, cookie=["loop_organizer=" + session + "; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800" + secure, "loop_demo=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0" + secure])
            elif path == "/api/logout":
                self.send(200, {"status": "signed_out"}, cookie=["loop_organizer=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0", "loop_demo=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"])
            elif path == "/api/reader/view":
                self.send(200, self.server.workspace.reader_view(body.get("token")))
            elif path == "/api/reader/accept":
                with self.server.workspace.lock:
                    cid, pid = self.server.workspace.reader_identity(body.get("token"))
                    self.server.workspace.accept(pid, True, body.get("proposal_id"), cid, "participant_link")
                self.send(200, {"status": "accepted"})
            elif path == "/api/reader/update":
                self.send(202, self.server.start_reader_job(body))
            elif path == "/api/reader/job":
                with self.server.workspace.lock:
                    self.server.workspace.reader_identity(body.get("token"))
                    job = self.server.get_job(body.get("job_id"))
                    require(job is not None and secrets.compare_digest(job.get("reader_key", ""), body["token"]), "This reader run is no longer available.")
                    self.send(200, {k: v for k, v in job.items() if k != "reader_key"})
            elif path == "/api/reader/search":
                with self.server.workspace.lock:
                    self.server.workspace.reader_identity(body.get("token"))
                    self.send(200, self.server.workspace.search(body.get("query"), body.get("type")))
            elif path == "/api/invites":
                invitations = self.server.workspace.invites(rotate=body.get("rotate") is True)
                if self.server.demo:
                    for reader in invitations["readers"]:
                        marker = hashlib.sha256(reader["token"].encode()).hexdigest()
                        self.root_server.workspace.store.write("demo-readers/" + marker + ".json", self.server.demo_identity)
                self.send(200, invitations)
            elif path == "/api/agent":
                self.send(202, self.server.start_job(body))
            elif path == "/api/accept":
                self.server.workspace.accept(body.get("participant_id"), body.get("accepted"), body.get("proposal_id"))
                self.send(200, {"status": "recorded", "simulated": self.server.workspace.state["fixture"]["provenance"] == "synthetic_test"})
            elif path == "/api/search":
                self.send(200, self.server.workspace.search(body.get("query"), body.get("type")))
            else:
                self.send(404, {"error": "Not found."})
        except (ExperimentError, ValueError, TypeError) as error:
            self.send(400, {"error": redact(str(error), self.server.workspace.secrets)})
        except Exception:
            self.send(503, {"error": "The workspace could not save this change. Try again shortly."})


def main():
    parser = argparse.ArgumentParser(description="Loop seeded book-exchange MVP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--workspace", default="local/loop-workspace")
    parser.add_argument("--restore-backup", help="Restore a downloaded backup into an empty workspace before starting.")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and len(os.getenv("LOOP_ADMIN_PASSWORD", "")) < 16:
        parser.error("Set a server-side LOOP_ADMIN_PASSWORD of at least 16 characters before hosting publicly.")
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        os.environ["LOOP_HOSTED"] = "1"
    directory = Path(args.workspace)
    directory.mkdir(parents=True, exist_ok=True)
    with workspace_lock(directory):
        if args.restore_backup:
            store = DocumentStore(directory)
            require(store.read("state.json") is None, "Restore into an empty workspace or database namespace to keep existing circles.")
            backup = read_json(args.restore_backup)
            require(backup.get("product") == "Loop" and backup.get("version") == 1 and backup.get("circles"), "Choose a Loop workspace backup.")
            docs = {}
            for state in backup["circles"]:
                validate_fixture(state["fixture"])
                require(identifier(state["fixture"]["id"]), "Invalid circle identifier.")
                require(validate_exchange(state["fixture"], state["proposal"], state["pool"], state["matrix"])["valid"], "The backup has an invalid proposal.")
                docs["circles/" + state["fixture"]["id"] + ".json"] = state
            docs.update({"state.json": backup["circles"][0], "live-rankings.json": backup.get("live_rankings", {}), "evidence.json": backup.get("evidence", [])})
            store.write_many(docs)
            evidence_path = directory / "evidence" / "requests.jsonl"
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in backup.get("evidence", [])), encoding="utf-8")
        workspace = Workspace(directory)
        server = LoopServer((args.host, args.port), workspace)
        print("Loop is ready at http://%s:%s" % (args.host, server.server_port), flush=True)
        print("Fictional shelf; genuine saved Qloo results. Server-side keys enable live search and Gemini chat.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
