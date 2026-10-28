import csv
import io
import re
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict, deque

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .auth import audit, current_profile, require, require_org
from .config import settings
from .db import sb
from .duplicates import DUP_COLS, analyze_duplicates, reduction_pct
from .features import (AUDIT_COLUMNS, DOC_COLUMNS, REGISTRY_COLUMNS, csv_response, expiry_report, filter_docs, find_records,
                       lookup_state, share_is_live)
from .pipeline import report_assets
from .registry import norm_ref
from .report import build_report
from .security import read_upload, safe_filename
from .service import REVIEW_STATUSES, SUMMARY_COLS, add_review, build_snapshot, process, publish, reverify, valid_uuid
from .stats import summarize

user_r = APIRouter(prefix="/api")
org_r = APIRouter(prefix="/api/org")
admin_r = APIRouter(prefix="/api/admin")
public_r = APIRouter(prefix="/api/public")  # no login: share-link viewing only

_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(uid: str, limit=10, window=600, bucket="upload"):
    q, now = _hits[f"{bucket}:{uid}"], time.time()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many requests. Try again in a few minutes." if bucket != "upload" else "Too many uploads. Try again in a few minutes.")
    q.append(now)


def _doc(doc_id: str) -> dict:
    rows = sb.table("documents").select("*").eq("id", valid_uuid(doc_id)).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Not found")
    return rows[0]


def _own(p: dict, doc_id: str) -> dict:
    d = _doc(doc_id)
    if d["user_id"] != p["id"] and p["role"] != "admin":
        raise HTTPException(404, "Not found")
    if p["role"] != "admin":
        d = {k: v for k, v in d.items() if k != "review_notes"}  # reviewers' notes are internal
    return d


def _org_doc(p: dict, doc_id: str) -> dict:
    d = _doc(doc_id)
    if d.get("org_id") != p["org_id"]:
        raise HTTPException(404, "Not found")
    d = {**d, "result": {k: v for k, v in d["result"].items() if k != "text_excerpt"}}
    return d


def _summaries(**eq):
    q = sb.table("documents").select(SUMMARY_COLS)
    for k, v in eq.items():
        q = q.eq(k, v)
    return q.order("created_at", desc=True).limit(2000).execute().data


# ------------------------------------------------------------------ everyone
@user_r.get("/me")
def me(p: dict = Depends(current_profile)):
    org = None
    if p.get("org_id"):
        rows = sb.table("organizations").select("id,name,status").eq("id", p["org_id"]).limit(1).execute().data
        org = rows[0] if rows else None
    return {"id": p["id"], "email": p["email"], "role": p["role"], "org": org}


@user_r.post("/analyze")
async def analyze_upload(file: UploadFile = File(...), p: dict = Depends(current_profile)):
    rate_limit(p["id"])
    data, ext, mime = await read_upload(file, settings.max_upload_mb * 1024 * 1024)
    return await run_in_threadpool(process, p, safe_filename(file.filename), data, ext, mime)


@user_r.get("/documents")
def list_documents(q: str = "", verdict: str = "", p: dict = Depends(current_profile)):
    return filter_docs(_summaries(user_id=p["id"]), q, verdict)[:100]


@user_r.get("/documents/export.csv")
def export_my_documents(p: dict = Depends(current_profile)):
    return csv_response("shastra-my-documents.csv", _summaries(user_id=p["id"]), ["filename", *DOC_COLUMNS])


def _dups(**eq):
    q = sb.table("documents").select(DUP_COLS)
    allrows = q.limit(5000).execute().data
    return allrows, [r for r in allrows if all(r.get(k) == v for k, v in eq.items())]


@user_r.get("/duplicates")
def my_duplicates(p: dict = Depends(current_profile)):
    allrows, mine = _dups(user_id=p["id"])
    return analyze_duplicates(allrows, mine)


@user_r.get("/lookup")
def lookup(ref: str, p: dict = Depends(current_profile)):
    """Exact reference-number lookup against approved issuers' registries. No upload needed.
    Exact match only (no prefix/fuzzy search) and rate-limited, so the registry cannot be enumerated."""
    rate_limit(p["id"], limit=30, bucket="lookup")
    if len(ref.strip()) < 5 or len(ref) > 80:
        raise HTTPException(422, "Enter the full reference number, e.g. Western/1-12345/2026/EOA")
    approved = {o["id"]: o["name"] for o in sb.table("organizations").select("id,name").eq("status", "approved").execute().data}
    recs = [r for r in sb.table("registry_records").select("*").execute().data if r["org_id"] in approved]
    today = date.today()
    hits = [{"reference_no": r["reference_no"], "institute_name": r["institute_name"], "academic_year": r.get("academic_year"),
             "valid_upto": r.get("valid_upto"), "courses": r.get("courses") or [], "issuer": approved[r["org_id"]],
             "state": lookup_state(r, today)} for r in find_records(ref, recs)]
    return {"found": bool(hits), "records": hits}


@user_r.get("/stats")
def my_stats(p: dict = Depends(current_profile)):
    return summarize(_summaries(user_id=p["id"]))


@user_r.get("/documents/{doc_id}")
def get_document(doc_id: str, p: dict = Depends(current_profile)):
    return _own(p, doc_id)


@user_r.post("/documents/{doc_id}/reverify")
def reverify_doc(doc_id: str, p: dict = Depends(current_profile)):
    return reverify(_own(p, doc_id), p)


@user_r.get("/documents/{doc_id}/file-url")
def file_url(doc_id: str, p: dict = Depends(current_profile)):
    row = _own(p, doc_id)
    res = sb.storage.from_(settings.supabase_bucket).create_signed_url(row["storage_path"], 60)
    return {"url": res.get("signedURL") or res.get("signedUrl")}


def _pdf(row: dict, who: str) -> Response:
    data = sb.storage.from_(settings.supabase_bucket).download(row["storage_path"])
    thumb, heat = report_assets(data, row["storage_path"].rsplit(".", 1)[-1])
    return Response(build_report(row, who, thumb, heat), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="shastra-report-{row["id"][:8]}.pdf"'})


@user_r.get("/documents/{doc_id}/report.pdf")
def report(doc_id: str, p: dict = Depends(current_profile)):
    return _pdf(_own(p, doc_id), p["email"] or "")


@user_r.delete("/documents/{doc_id}")
def delete_document(doc_id: str, p: dict = Depends(current_profile)):
    row = _own(p, doc_id)
    sb.storage.from_(settings.supabase_bucket).remove([row["storage_path"]])
    sb.table("share_links").delete().eq("document_id", row["id"]).execute()
    sb.table("documents").delete().eq("id", row["id"]).execute()
    audit(p, "document.delete", row["id"])
    return {"deleted": True}


@user_r.get("/published")
def published(p: dict = Depends(current_profile)):
    rows = sb.table("published_reports").select("*").eq("status", "published").order("created_at", desc=True).limit(200).execute().data
    return [r for r in rows if r["scope"] == "public" or p["role"] == "admin" or (p.get("org_id") and r.get("org_id") == p["org_id"])]


# ------------------------------------------------------------------ share links
@user_r.post("/documents/{doc_id}/share")
def create_share(doc_id: str, body: dict = Body(default={}), p: dict = Depends(current_profile)):
    row = _own(p, doc_id)
    try:
        days = int(body.get("days", 7))
    except (TypeError, ValueError):
        raise HTTPException(422, "days must be a number")
    if not 1 <= days <= 90:
        raise HTTPException(422, "days must be between 1 and 90")
    live = [x for x in sb.table("share_links").select("*").eq("document_id", row["id"]).execute().data if share_is_live(x)]
    if len(live) >= 5:
        raise HTTPException(409, "This document already has 5 active share links. Revoke one first.")
    link = {"token": secrets.token_urlsafe(24), "document_id": row["id"], "user_id": row["user_id"], "revoked": False, "views": 0,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(), "snapshot": build_snapshot(row)}
    out = sb.table("share_links").insert(link).execute().data[0]
    audit(p, "share.create", row["id"], {"days": days})
    return out


@user_r.get("/documents/{doc_id}/shares")
def list_shares(doc_id: str, p: dict = Depends(current_profile)):
    row = _own(p, doc_id)
    rows = sb.table("share_links").select("*").eq("document_id", row["id"]).order("created_at", desc=True).execute().data
    return [{**{k: v for k, v in x.items() if k != "snapshot"}, "live": share_is_live(x)} for x in rows]


@user_r.delete("/shares/{share_id}")
def revoke_share(share_id: str, p: dict = Depends(current_profile)):
    rows = sb.table("share_links").select("*").eq("id", valid_uuid(share_id)).limit(1).execute().data
    if not rows or (rows[0]["user_id"] != p["id"] and p["role"] != "admin"):
        raise HTTPException(404, "Not found")
    sb.table("share_links").update({"revoked": True}).eq("id", share_id).execute()
    audit(p, "share.revoke", share_id)
    return {"revoked": True}


@public_r.get("/share/{token}")
def view_share(token: str, request: Request):
    """Unauthenticated, read-only. Returns only the identity-free snapshot; every failure looks the same (404)."""
    rate_limit(request.client.host if request.client else "unknown", limit=60, bucket="share")
    rows = sb.table("share_links").select("*").eq("token", token[:80]).limit(1).execute().data
    if not rows or not share_is_live(rows[0]):
        raise HTTPException(404, "This link is invalid, expired or has been revoked")
    link = rows[0]
    sb.table("share_links").update({"views": int(link.get("views") or 0) + 1}).eq("id", link["id"]).execute()
    return {"snapshot": link["snapshot"], "shared_at": link["created_at"], "expires_at": link["expires_at"]}


# ------------------------------------------------------------------ organization
REG_COLS = ("reference_no", "institute_name", "academic_year", "issue_date", "valid_upto", "permanent_id", "courses", "sha256", "expected_watermark", "notes")


def _clean_record(raw: dict) -> dict:
    rec = {k: (str(raw.get(k)).strip() if raw.get(k) not in (None, "") and k != "courses" else None) for k in REG_COLS if k != "courses"}
    c = raw.get("courses") or []
    rec["courses"] = [x.strip() for x in (re.split(r"[;|]", c) if isinstance(c, str) else c) if str(x).strip()][:30]
    if not rec["reference_no"] or not rec["institute_name"]:
        raise HTTPException(422, "reference_no and institute_name are required")
    if rec["sha256"] and not re.fullmatch(r"[0-9a-fA-F]{64}", rec["sha256"]):
        raise HTTPException(422, "sha256 must be 64 hex characters")
    rec["sha256"] = rec["sha256"].lower() if rec["sha256"] else None
    return rec


@org_r.get("/registry")
def reg_list(p: dict = Depends(require_org)):
    return sb.table("registry_records").select("*").eq("org_id", p["org_id"]).order("created_at", desc=True).limit(1000).execute().data


@org_r.get("/registry/export.csv")
def reg_export(p: dict = Depends(require_org)):
    return csv_response("shastra-registry.csv", reg_list(p), REGISTRY_COLUMNS)  # same column names the importer reads


@org_r.post("/registry")
def reg_add(body: dict = Body(...), p: dict = Depends(require_org)):
    rec = {**_clean_record(body), "org_id": p["org_id"], "status": "active", "created_by": p["id"]}
    out = sb.table("registry_records").insert(rec).execute().data[0]
    audit(p, "registry.add", out["id"], {"ref": rec["reference_no"]})
    return out


@org_r.post("/registry/import")
def reg_import(body: dict = Body(...), p: dict = Depends(require_org)):
    rows = list(csv.DictReader(io.StringIO(str(body.get("csv", "")))))[:500]
    ok, errors = [], []
    existing = {norm_ref(r["reference_no"]) for r in reg_list(p)}
    for i, raw in enumerate(rows, start=2):
        try:
            rec = _clean_record({k.strip().lower(): v for k, v in raw.items() if k})
            if norm_ref(rec["reference_no"]) in existing:
                raise HTTPException(409, "duplicate reference_no")
            existing.add(norm_ref(rec["reference_no"]))
            ok.append({**rec, "org_id": p["org_id"], "status": "active", "created_by": p["id"]})
        except HTTPException as e:
            errors.append({"line": i, "error": e.detail})
    if ok:
        sb.table("registry_records").insert(ok).execute()
    audit(p, "registry.import", None, {"added": len(ok), "errors": len(errors)})
    return {"added": len(ok), "errors": errors}


def _rec(p, rid):
    rows = sb.table("registry_records").select("*").eq("id", valid_uuid(rid)).eq("org_id", p["org_id"]).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Not found")
    return rows[0]


@org_r.patch("/registry/{rid}")
def reg_status(rid: str, body: dict = Body(...), p: dict = Depends(require_org)):
    """Revoke / reinstate (body {"status"}) and/or edit the record's fields (any of REG_COLS)."""
    cur = _rec(p, rid)
    upd = {}
    if "status" in body:
        if body["status"] not in ("active", "revoked"):
            raise HTTPException(422, "status must be active or revoked")
        upd["status"] = body["status"]
    if any(k in body for k in REG_COLS):
        rec = _clean_record({**{k: cur.get(k) for k in REG_COLS}, **{k: body[k] for k in REG_COLS if k in body}})
        if any(norm_ref(r["reference_no"]) == norm_ref(rec["reference_no"]) and r["id"] != rid for r in reg_list(p)):
            raise HTTPException(409, "Another record already uses this reference number")
        upd.update(rec)
    if not upd:
        raise HTTPException(422, "Nothing to update")
    sb.table("registry_records").update(upd).eq("id", rid).execute()
    audit(p, "registry.edit" if len(upd) > 1 or "status" not in upd else f"registry.{upd['status']}", rid)
    return {"ok": True}


@org_r.delete("/registry/{rid}")
def reg_delete(rid: str, p: dict = Depends(require_org)):
    _rec(p, rid)
    sb.table("registry_records").delete().eq("id", rid).execute()
    audit(p, "registry.delete", rid)
    return {"deleted": True}


@org_r.get("/documents")
def org_docs(p: dict = Depends(require_org)):
    return [{k: v for k, v in d.items() if k not in ("user_id", "filename")} for d in _summaries(org_id=p["org_id"])]


@org_r.get("/documents/export.csv")
def org_export(p: dict = Depends(require_org)):
    return csv_response("shastra-submissions.csv", _summaries(org_id=p["org_id"]), DOC_COLUMNS)  # no filename / uploader


@org_r.post("/documents/{doc_id}/review")
def org_review(doc_id: str, body: dict = Body(...), p: dict = Depends(require_org)):
    return add_review(p, _org_doc(p, doc_id), body)


@org_r.get("/documents/{doc_id}")
def org_doc(doc_id: str, p: dict = Depends(require_org)):
    d = _org_doc(p, doc_id)
    d.pop("user_id", None)
    return d


@org_r.get("/duplicates")
def org_duplicates(p: dict = Depends(require_org)):
    allrows, mine = _dups(org_id=p["org_id"])
    return analyze_duplicates(allrows, mine, expose_identity=False)  # uploader-blind, no file names


@org_r.get("/stats")
def org_stats(p: dict = Depends(require_org)):
    docs = _summaries(org_id=p["org_id"])
    s = summarize(docs)
    recs = reg_list(p)
    s["registry"] = {"total": len(recs), "revoked": sum(r["status"] == "revoked" for r in recs), **expiry_report(recs, date.today())}
    s["review"] = {k: sum(d.get("review_status") == k for d in docs) for k in REVIEW_STATUSES}
    return s


@org_r.post("/documents/{doc_id}/publish")
def org_publish(doc_id: str, body: dict = Body(...), p: dict = Depends(require_org)):
    out = publish(p, _org_doc(p, doc_id), body.get("title", ""), body.get("note", ""), body.get("scope", "org"))
    audit(p, "report.publish", out["id"])
    return out


# ------------------------------------------------------------------ admin
admin = Depends(require("admin"))


@admin_r.get("/stats")
def admin_stats(p: dict = admin):
    s = summarize(_summaries())
    users = sb.table("profiles").select("id,role").limit(5000).execute().data
    orgs = sb.table("organizations").select("id,status").limit(2000).execute().data
    reps = sb.table("published_reports").select("id,status").limit(5000).execute().data
    s["users"] = {r: sum(u["role"] == r for u in users) for r in ("user", "org", "admin")}
    s["orgs"] = {st: sum(o["status"] == st for o in orgs) for st in ("pending", "approved", "suspended")}
    s["reports"] = {"published": sum(r["status"] == "published" for r in reps), "withdrawn": sum(r["status"] == "withdrawn" for r in reps)}
    return s


@admin_r.get("/duplicates")
def admin_duplicates(p: dict = admin):
    allrows, _ = _dups()
    return analyze_duplicates(allrows, allrows)


def _impact_view():
    rows = sb.table("impact_baselines").select("*").order("created_at", desc=True).limit(1).execute().data
    base = rows[0] if rows else None
    allrows, _ = _dups()
    post = None
    if base:
        post_rows = [r for r in allrows if (r["created_at"] or "")[:10] >= base["post_start"]]
        post = analyze_duplicates(allrows, post_rows)["duplicate_files"]
    return {"baseline": base, "post_duplicate_cases": post,
            "reduction_pct": reduction_pct(base["baseline_duplicate_cases"], post) if base else None,
            "formula": "Reduction (%) = ((Baseline duplicate cases - Post-deployment duplicate cases) / Baseline duplicate cases) x 100"}


@admin_r.get("/impact")
def admin_impact(p: dict = admin):
    return _impact_view()


@admin_r.put("/impact")
def admin_impact_set(body: dict = Body(...), p: dict = admin):
    """Record the MEASURED baseline from the pre-deployment process. post_start = ISO date the pilot began."""
    try:
        n = int(body["baseline_duplicate_cases"]); period = str(body["period_label"]).strip()[:120]; start = str(body["post_start"])[:10]
        date.fromisoformat(start)
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "baseline_duplicate_cases (integer), period_label and post_start (YYYY-MM-DD) are required")
    if n <= 0 or not period:
        raise HTTPException(422, "baseline_duplicate_cases must be a positive number and period_label is required")
    sb.table("impact_baselines").insert({"baseline_duplicate_cases": n, "period_label": period, "post_start": start,
                                         "source_note": str(body.get("source_note") or "")[:500], "set_by": p["id"]}).execute()
    audit(p, "impact.baseline", None, {"baseline": n, "post_start": start})
    return _impact_view()


@admin_r.get("/users")
def admin_users(p: dict = admin):
    return sb.table("profiles").select("*").order("created_at", desc=True).limit(500).execute().data


@admin_r.patch("/users/{uid}")
def admin_user_update(uid: str, body: dict = Body(...), p: dict = admin):
    valid_uuid(uid)
    upd = {}
    if body.get("role") in ("user", "org", "admin"):
        upd["role"] = body["role"]
    if body.get("status") in ("active", "suspended"):
        upd["status"] = body["status"]
    if uid == p["id"] or not upd:
        raise HTTPException(422, "Nothing to change (you cannot modify your own account here)")
    sb.table("profiles").update(upd).eq("id", uid).execute()
    audit(p, "user.update", uid, upd)
    return {"ok": True}


@admin_r.get("/orgs")
def admin_orgs(p: dict = admin):
    return sb.table("organizations").select("*").order("created_at", desc=True).limit(500).execute().data


@admin_r.patch("/orgs/{oid}")
def admin_org_update(oid: str, body: dict = Body(...), p: dict = admin):
    valid_uuid(oid)
    if body.get("status") not in ("approved", "suspended", "pending"):
        raise HTTPException(422, "Invalid status")
    sb.table("organizations").update({"status": body["status"]}).eq("id", oid).execute()
    audit(p, f"org.{body['status']}", oid)
    return {"ok": True}


@admin_r.get("/documents")
def admin_docs(p: dict = admin):
    return _summaries()


@admin_r.get("/documents/export.csv")
def admin_export(p: dict = admin):
    return csv_response("shastra-all-documents.csv", _summaries(), ["filename", "user_id", "org_id", *DOC_COLUMNS])


@admin_r.post("/documents/{doc_id}/review")
def admin_review(doc_id: str, body: dict = Body(...), p: dict = admin):
    return add_review(p, _doc(doc_id), body)


@admin_r.get("/documents/{doc_id}")
def admin_doc(doc_id: str, p: dict = admin):
    return _doc(doc_id)


@admin_r.get("/documents/{doc_id}/report.pdf")
def admin_report(doc_id: str, p: dict = admin):
    return _pdf(_doc(doc_id), p["email"] or "")


@admin_r.post("/documents/{doc_id}/publish")
def admin_publish(doc_id: str, body: dict = Body(...), p: dict = admin):
    out = publish(p, _doc(doc_id), body.get("title", ""), body.get("note", ""), body.get("scope", "public"))
    audit(p, "report.publish", out["id"])
    return out


@admin_r.get("/reports")
def admin_reports(p: dict = admin):
    return sb.table("published_reports").select("*").order("created_at", desc=True).limit(500).execute().data


@admin_r.patch("/reports/{rid}")
def admin_report_update(rid: str, body: dict = Body(...), p: dict = admin):
    valid_uuid(rid)
    if body.get("status") not in ("published", "withdrawn"):
        raise HTTPException(422, "Invalid status")
    sb.table("published_reports").update({"status": body["status"]}).eq("id", rid).execute()
    audit(p, f"report.{body['status']}", rid)
    return {"ok": True}


@admin_r.get("/audit/export.csv")
def admin_audit_export(p: dict = admin):
    rows = sb.table("audit_log").select("*").order("created_at", desc=True).limit(5000).execute().data
    return csv_response("shastra-audit-log.csv", rows, AUDIT_COLUMNS)


@admin_r.get("/audit")
def admin_audit(p: dict = admin):
    return sb.table("audit_log").select("*").order("created_at", desc=True).limit(200).execute().data
