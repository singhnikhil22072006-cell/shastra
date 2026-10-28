"""Helpers for the v2 features: CSV export, registry lookup, document filtering, expiry alerts, share-link checks."""
import csv
import io
from datetime import date, datetime, timedelta, timezone

from fastapi.responses import Response

from .parser import parse_date
from .registry import norm_ref

# --------------------------------------------------------------------------- CSV export
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(v) -> str:
    """Neutralise spreadsheet formula injection: a cell starting with = + - @ is prefixed with an apostrophe."""
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        v = "; ".join(str(x) for x in v)
    elif isinstance(v, dict):
        v = ", ".join(f"{k}={x}" for k, x in v.items())
    s = str(v)
    return "'" + s if s.startswith(_FORMULA_START) else s


def csv_response(filename: str, rows: list[dict], columns: list[str]) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rows:
        w.writerow([csv_safe(r.get(c)) for c in columns])
    # BOM so Excel opens UTF-8 correctly
    return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


DOC_COLUMNS = ["created_at", "reference_no", "institute_name", "academic_year", "verification_status", "trust_score",
               "risk_level", "risk_score", "review_status"]
AUDIT_COLUMNS = ["created_at", "actor_email", "action", "target", "meta"]
REGISTRY_COLUMNS = ["reference_no", "institute_name", "academic_year", "issue_date", "valid_upto", "permanent_id",
                    "courses", "sha256", "expected_watermark", "status", "notes"]

# --------------------------------------------------------------------------- history search / filter
VERDICTS = ("VERIFIED", "PARTIAL", "UNVERIFIED", "SUSPICIOUS", "MISMATCH")


def filter_docs(rows: list[dict], q: str = "", verdict: str = "") -> list[dict]:
    q = (q or "").strip().lower()[:100]
    verdict = (verdict or "").strip().upper()
    out = rows
    if verdict == "FLAGGED":
        out = [r for r in out if r.get("verification_status") in ("MISMATCH", "SUSPICIOUS")]
    elif verdict in VERDICTS:
        out = [r for r in out if (r.get("verification_status") or "UNVERIFIED") == verdict]
    if q:
        keys = ("filename", "reference_no", "institute_name", "academic_year")
        out = [r for r in out if any(q in str(r.get(k) or "").lower() for k in keys)]
    return out


# --------------------------------------------------------------------------- registry lookup
def lookup_state(rec: dict, today: date) -> str:
    if rec.get("status") == "revoked":
        return "REVOKED"
    valid = parse_date(rec.get("valid_upto") or "")
    if valid and valid < today:
        return "EXPIRED"
    return "ACTIVE"


def find_records(ref: str, records: list[dict]) -> list[dict]:
    n = norm_ref(ref)
    return [r for r in records if norm_ref(r["reference_no"]) == n] if n else []


# --------------------------------------------------------------------------- registry expiry alerts
def expiry_report(records: list[dict], today: date, window_days: int = 60) -> dict:
    soon, expired = [], 0
    limit = today + timedelta(days=window_days)
    for r in records:
        if r.get("status") != "active":
            continue
        d = parse_date(r.get("valid_upto") or "")
        if not d:
            continue
        if d < today:
            expired += 1
        elif d <= limit:
            soon.append({"id": r["id"], "reference_no": r["reference_no"], "institute_name": r["institute_name"],
                         "valid_upto": str(d), "days_left": (d - today).days})
    soon.sort(key=lambda x: x["days_left"])
    return {"expiring_soon": soon[:50], "expired_active": expired, "window_days": window_days}


# --------------------------------------------------------------------------- share links
def share_is_live(link: dict, now: datetime | None = None) -> bool:
    if link.get("revoked"):
        return False
    try:
        exp = datetime.fromisoformat(str(link["expires_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return False  # unparsable expiry => treat as expired (fail closed)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > (now or datetime.now(timezone.utc))
