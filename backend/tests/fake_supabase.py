"""Tiny in-memory stand-in for the supabase-py calls this app uses. For tests only."""
import types
import uuid
from datetime import datetime, timezone

DEFAULTS = {"status": None}


class Q:
    def __init__(self, db, name):
        self.db, self.name, self.op, self.payload = db, name, "select", None
        self.filters, self.ord, self.lim = [], None, None

    def select(self, *_):
        self.op = "select"; return self
    def insert(self, p):
        self.op, self.payload = "insert", p; return self
    def update(self, p):
        self.op, self.payload = "update", p; return self
    def delete(self):
        self.op = "delete"; return self
    def eq(self, k, v):
        self.filters.append((k, v)); return self
    def order(self, k, desc=False):
        self.ord = (k, desc); return self
    def limit(self, n):
        self.lim = n; return self

    def execute(self):
        rows = self.db.tables.setdefault(self.name, [])
        match = lambda r: all(r.get(k) == v for k, v in self.filters)  # noqa: E731
        if self.op == "insert":
            items = self.payload if isinstance(self.payload, list) else [self.payload]
            out = []
            for it in items:
                r = {"id": str(uuid.uuid4()) if self.name != "audit_log" else len(rows) + 1,
                     "created_at": datetime.now(timezone.utc).isoformat(), "status": "active", **it}
                if self.name == "organizations":
                    r.setdefault("status", "pending")
                rows.append(r); out.append(dict(r))
            return types.SimpleNamespace(data=out)
        if self.op == "update":
            hit = [r for r in rows if match(r)]
            for r in hit:
                r.update(self.payload)
            return types.SimpleNamespace(data=[dict(r) for r in hit])
        if self.op == "delete":
            self.db.tables[self.name] = [r for r in rows if not match(r)]
            return types.SimpleNamespace(data=[])
        out = [dict(r) for r in rows if match(r)]
        if self.ord:
            out.sort(key=lambda r: str(r.get(self.ord[0])), reverse=self.ord[1])
        return types.SimpleNamespace(data=out[: self.lim] if self.lim else out)


class Storage:
    def __init__(self): self.files = {}
    def from_(self, _): return self
    def upload(self, path, data, _=None): self.files[path] = data
    def download(self, path): return self.files[path]
    def remove(self, paths): [self.files.pop(p, None) for p in paths]
    def create_signed_url(self, path, _): return {"signedURL": "http://signed/" + path}


class FakeSB:
    def __init__(self):
        self.tables, self.storage, self.users = {}, Storage(), {}
        self.auth = types.SimpleNamespace(get_user=self._get_user)

    def table(self, name): return Q(self, name)

    def add_user(self, token, email, confirmed=True, meta=None):
        self.users[token] = types.SimpleNamespace(id=str(uuid.uuid4()), email=email,
                                                  email_confirmed_at="2026-01-01" if confirmed else None, user_metadata=meta or {})
        return self.users[token]

    def _get_user(self, token):
        if token not in self.users:
            raise Exception("bad token")
        return types.SimpleNamespace(user=self.users[token])
