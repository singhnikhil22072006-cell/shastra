"""Duplicate / inconsistency analysis built only from stored document rows (real data, nothing synthetic).

Categories (a repeat is NOT treated as fraud):
  repeated_submission  same file (SHA-256) uploaded again by the same account
  shared_file          same file present in several accounts (common: one letter, many applicants)
  new_version          same reference number + institute, different file, no conflicting fields
  conflict             same reference number but institute / academic year / validity differ
Only `conflict` groups are marked needs_review; the rest are informational.
"""
from collections import defaultdict

from .parser import parse_date
from .registry import _alnum, norm_ref

DUP_COLS = "id,user_id,org_id,filename,sha256,reference_no,institute_name,academic_year,valid_upto,verification_status,review_status,created_at"
KINDS = ("repeated_submission", "shared_file", "new_version", "conflict")
EXPLAIN = {
    "repeated_submission": "The same file was submitted more than once by one account. Usually harmless; check whether an older result is still current.",
    "shared_file": "The identical file exists in more than one account. Letters are often shared, so this alone is not a problem.",
    "new_version": "Same reference number and institute but a different file. Could be a re-scan or a re-issued letter; compare the versions.",
    "conflict": "Same reference number but conflicting details across documents. A reviewer should compare the evidence.",
}


def _diffs(rows: list[dict]) -> list[str]:
    out = []
    if len({_alnum(r.get("institute_name")) for r in rows if r.get("institute_name")}) > 1:
        out.append("institute_name")
    if len({_alnum(r.get("academic_year")) for r in rows if r.get("academic_year")}) > 1:
        out.append("academic_year")
    if len({str(parse_date(r["valid_upto"])) for r in rows if r.get("valid_upto") and parse_date(r["valid_upto"])}) > 1:
        out.append("valid_upto")
    return out


def analyze_duplicates(all_rows: list[dict], visible: list[dict], expose_identity: bool = True) -> dict:
    """all_rows: every stored row (for cross-account context). visible: rows the caller may see."""
    vis_ids = {r["id"] for r in visible}
    by_sha, by_ref = defaultdict(list), defaultdict(list)
    for r in all_rows:
        by_sha[r["sha256"]].append(r)
        if norm_ref(r.get("reference_no")):
            by_ref[norm_ref(r["reference_no"])].append(r)
    groups, seen = [], set()

    def member(r):
        m = {"id": r["id"], "verdict": r.get("verification_status") or "UNVERIFIED", "created_at": r["created_at"],
             "reference_no": r.get("reference_no"), "institute_name": r.get("institute_name"), "academic_year": r.get("academic_year")}
        if expose_identity:
            m["filename"] = r.get("filename")
        return m

    for sha, rows in by_sha.items():
        mine = [r for r in rows if r["id"] in vis_ids]
        if not mine or len(rows) < 2:
            continue
        users = {r["user_id"] for r in rows}
        kind = "repeated_submission" if len({r["user_id"] for r in mine}) == 1 and len(mine) > 1 else "shared_file"
        if kind == "shared_file" and len(users) < 2:
            continue
        seen.update(r["id"] for r in rows)
        groups.append({"kind": kind, "key": sha[:12], "count": len(rows), "visible_count": len(mine), "needs_review": False,
                       "explanation": EXPLAIN[kind], "members": [member(r) for r in mine]})

    for ref, rows in by_ref.items():
        distinct = {r["sha256"] for r in rows}
        mine = [r for r in rows if r["id"] in vis_ids]
        if len(distinct) < 2 or not mine:
            continue
        diffs = _diffs(rows)
        kind = "conflict" if diffs else "new_version"
        groups.append({"kind": kind, "key": ref[:24], "count": len(rows), "visible_count": len(mine), "differs_in": diffs,
                       "needs_review": kind == "conflict", "explanation": EXPLAIN[kind], "members": [member(r) for r in mine]})

    counts = {k: sum(g["kind"] == k for g in groups) for k in KINDS}
    extra = sum(g["count"] - 1 for g in groups if g["kind"] in ("repeated_submission", "shared_file"))
    return {"total_documents": len(visible), "groups": sorted(groups, key=lambda g: (not g["needs_review"], g["kind"])),
            "counts": counts, "duplicate_files": extra,
            "awaiting_review": sum(1 for r in visible if r.get("review_status") in ("flagged", "under_review")),
            "avg_verification_seconds": None,
            "avg_verification_note": "Not measured yet: the current build does not record per-document processing time."}


def reduction_pct(baseline: int, post: int):
    """Reduction (%) = ((baseline - post) / baseline) * 100. None when no valid baseline exists."""
    return None if not baseline or baseline <= 0 or post is None or post < 0 else round((baseline - post) / baseline * 100, 1)
