"""Local, credential-redacted evidence and one active experiment per workspace."""

import hashlib
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class ExperimentError(ValueError):
    pass


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def digest(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def fixture_hash(fixture):
    return digest({key: value for key, value in fixture.items() if key != "frozen_hash"})


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {key: ("[REDACTED]" if any(word in key.lower().replace("-", "_")
                    for word in ("api_key", "authorization", "password", "access_token", "secret"))
                    else redact(item, secrets)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    return value


def safe_url(url):
    parts = urlsplit(url)
    query = [(key, "[REDACTED]" if key.lower() in ("key", "api_key", "token") else value)
             for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


class Evidence:
    def __init__(self, directory, secrets=()):
        self.path = Path(directory) / "requests.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.secrets = tuple(secret for secret in secrets if secret)
        self.count = sum(1 for _ in self.path.open(encoding="utf-8")) if self.path.exists() else 0

    def record(self, event):
        self.count += 1
        evidence_id = "request-%04d" % self.count
        event = redact(dict(event, evidence_id=evidence_id), self.secrets)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
        return evidence_id


@contextmanager
def workspace_lock(root):
    path = Path(root) / ".shootout.lock"
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ExperimentError("An experiment is already active. If its process ended, remove %s." % path)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)
