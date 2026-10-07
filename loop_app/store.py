"""Small JSON document store: local files, or Postgres for hosted circles."""
import json
import os
import secrets
from pathlib import Path

from shootout.storage import Evidence, read_json


class DocumentStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.url = os.getenv("LOOP_DATABASE_URL")
        self.namespace = os.getenv("LOOP_DATABASE_NAMESPACE", "loop")
        if self.url:
            import psycopg
            from psycopg.types.json import Jsonb
            self.connect = psycopg.connect
            self.jsonb = Jsonb
            with self.connect(self.url, connect_timeout=15) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS loop_documents (namespace TEXT NOT NULL, name TEXT NOT NULL, payload JSONB NOT NULL, PRIMARY KEY(namespace, name))")

    def read(self, name, default=None):
        if self.url:
            with self.connect(self.url, connect_timeout=15) as conn:
                row = conn.execute("SELECT payload FROM loop_documents WHERE namespace=%s AND name=%s", (self.namespace, name)).fetchone()
                return row[0] if row else default
        path = self.directory / name
        return read_json(path) if path.exists() else default

    def write(self, name, value):
        self.write_many({name: value})

    def write_many(self, values):
        if self.url:
            with self.connect(self.url, connect_timeout=15) as conn:
                for name, value in values.items():
                    conn.execute("INSERT INTO loop_documents(namespace,name,payload) VALUES(%s,%s,%s) ON CONFLICT(namespace,name) DO UPDATE SET payload=EXCLUDED.payload", (self.namespace, name, self.jsonb(value)))
        else:
            for name, value in values.items():
                path = self.directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_name(path.name + "." + secrets.token_hex(4) + ".tmp")
                descriptor = os.open(str(temp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                try:
                    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
                        handle.write("\n")
                    os.replace(temp, path)
                finally:
                    temp.unlink(missing_ok=True)

    def names(self, prefix):
        if self.url:
            with self.connect(self.url, connect_timeout=15) as conn:
                return [row[0] for row in conn.execute("SELECT name FROM loop_documents WHERE namespace=%s AND starts_with(name,%s) ORDER BY name", (self.namespace, prefix)).fetchall()]
        return sorted(str(path.relative_to(self.directory)) for path in (self.directory / prefix).glob("*.json"))


class SavedEvidence(Evidence):
    """Persist redacted provider responses on hosts with ephemeral filesystems."""
    def __init__(self, directory, store, secrets=()):
        self.store = store
        if store.url:
            path = Path(directory) / "requests.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            rows = store.read("evidence.json", [])
            path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        super().__init__(directory, secrets)

    def record(self, event):
        evidence_id = super().record(event)
        if self.store.url:
            rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]
            self.store.write("evidence.json", rows)
        return evidence_id
