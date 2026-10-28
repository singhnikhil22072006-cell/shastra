"""Shared operations used by the user / org / admin routes."""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from .config import settings
from .db import sb
from .pipeline import analyze
from .stats import finding_counts

REVIEW_STATUSES = ("flagged", "under_review", "resolved", "dismissed")
SUMMARY_COLS = "id,user_id,org_id,filename,risk_score,risk_level,verification_status,trust_score,reference_no,institute_name,academic_year,review_status,finding_counts,created_at"


def valid_uuid(x: str) -> str:
    try:
        uuid.UUID(x)
    except ValueError:
        raise HTTPException(404, "Not found")
    return x


def load_context(user_id: str):
    stored = (sb.table("documents").select("id,user_id,filename,sha256,reference_no,institute_name,academic_year,valid_upto,created_at")
              .limit(2000).execute().data)
    registry = sb.table("registry_records").select("*").limit(5000).execute().data
    approved = {o["id"] for o in sb.table("organizations").select("id").eq("status", "approved").execute().data}
    return stored, [r for r in registry if r["org_id"] in approved]


def _row_fields(result: dict) -> dict:
    f, m = result["fields"], result["registry_match"]
    v = result["verification"]
    return {"reference_no": f["reference_no"]["value"] if f["reference_no"] else None,
            "institute_name": f["institute_name"]["value"] if f["institute_name"] else None,
            "academic_year": f["academic_year"]["value"] if f["academic_year"] else None,
            "valid_upto": f["valid_upto"]["value"] if f["valid_upto"] else None,
            "risk_score": result["risk"]["score"], "risk_level": result["risk"]["level"],
            "verification_status": v["status"], "trust_score": v["trust_score"],
            "org_id": m["record"]["org_id"] if m["matched"] else None,
            "review_status": "flagged" if v["status"] in ("MISMATCH", "SUSPICIOUS") else "clear",
            "finding_counts": finding_counts(result["findings"]), "result": result}


def process(user: dict, filename: str, data: bytes, ext: str, mime: str) -> dict:
    stored, registry = load_context(user["id"])
    try:
        result = analyze(data, ext, mime, filename, user["id"], stored, registry)
    except ValueError as e:
        raise HTTPException(422, str(e))
    doc_id = str(uuid.uuid4())
    path = f"{user['id']}/{doc_id}.{ext}"  # server-generated: user filename never touches storage paths
    sb.storage.from_(settings.supabase_bucket).upload(path, data, {"content-type": mime})
    row = {"id": doc_id, "user_id": user["id"], "filename": filename, "sha256": result["file"]["sha256"],
           "storage_path": path, "mime": mime, **_row_fields(result)}
    sb.table("documents").insert(row).execute()
    return row


def reverify(row: dict, user: dict) -> dict:
    """Re-run analysis on the stored file, e.g. after an organization added its registry records."""
    data = sb.storage.from_(settings.supabase_bucket).download(row["storage_path"])
    stored, registry = load_context(user["id"])
    stored = [d for d in stored if d["id"] != row["id"]]
    result = analyze(data, row["storage_path"].rsplit(".", 1)[-1], row["mime"], row["filename"], row["user_id"], stored, registry)
    upd = _row_fields(result)
    if row.get("review_status") in ("under_review", "resolved", "dismissed", "published"):
        upd.pop("review_status")  # re-verifying must not undo a reviewer's decision
    sb.table("documents").update(upd).eq("id", row["id"]).execute()
    return {**row, **upd}


def build_snapshot(row: dict) -> dict:
    """Identity-free summary of a verification (no file name, no uploader). Used for publishing and share links."""
    r = row["result"]
    v = r["verification"]
    return {
        "reference_no": row.get("reference_no"), "institute_name": row.get("institute_name"), "academic_year": row.get("academic_year"),
        "verdict": v["status"], "trust_score": v["trust_score"], "risk_level": r["risk"]["level"], "summary": v["summary"],
        "signals": [{"label": s["label"], "state": s["state"]} for s in v["signals"]],
        "findings": [{"severity": f["severity"], "category": f["category"], "title": f["title"], "detail": f["detail"]}
                     for f in r["findings"] if f["severity"] in ("high", "medium")][:20],
        "mismatches": r["registry_match"]["diffs"],
    }


def publish(actor: dict, row: dict, title: str, note: str, scope: str) -> dict:
    snap = build_snapshot(row)
    rep = {"document_id": row["id"], "org_id": row.get("org_id"), "published_by": actor["id"], "published_by_email": actor["email"],
           "title": title.strip()[:160] or f"Report {row.get('reference_no') or row['id'][:8]}", "note": note.strip()[:2000],
           "scope": scope if scope in ("public", "org") else "public", "status": "published", "snapshot": snap}
    out = sb.table("published_reports").insert(rep).execute().data[0]
    sb.table("documents").update({"review_status": "published"}).eq("id", row["id"]).execute()
    return out


def add_review(actor: dict, row: dict, body: dict) -> dict:
    """Move a document through the review workflow and append an internal note (visible to org/admin only)."""
    status = body.get("status")
    if status not in REVIEW_STATUSES:
        raise HTTPException(422, f"status must be one of: {', '.join(REVIEW_STATUSES)}")
    note = str(body.get("note") or "").strip()[:1000]
    notes = list(row.get("review_notes") or [])[-99:]
    notes.append({"at": datetime.now(timezone.utc).isoformat(), "by": actor["email"], "role": actor["role"], "status": status, "note": note})
    sb.table("documents").update({"review_status": status, "review_notes": notes}).eq("id", row["id"]).execute()
    from .auth import audit  # local import: auth has no dependency on service
    audit(actor, f"review.{status}", row["id"])
    return {"review_status": status, "review_notes": notes}
