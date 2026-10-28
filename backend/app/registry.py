"""Match an analysed document against organization-issued registry records and flag regulatory problems.

The registry is the only source here that can say "the issuer really issued this". Every comparison is
field-by-field and reported as a diff, so the user sees exactly what disagrees.
"""
import re
from datetime import date
from difflib import SequenceMatcher

from .parser import COURSE_RX, parse_date


def norm_ref(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9/\-]", "", (s or "").upper())


def _alnum(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _prog(s: str) -> set[str]:
    return {re.sub(r"[^a-z]", "", m.group(1).lower()) for m in re.finditer(COURSE_RX, s or "", re.I)}


def current_ay_start(today: date) -> int:
    return today.year if today.month >= 6 else today.year - 1


PUBLIC_KEYS = ("id", "org_id", "reference_no", "institute_name", "academic_year", "valid_upto", "status", "expected_watermark")


def match_registry(parsed: dict, sha: str, records: list[dict]) -> dict:
    f = parsed["fields"]
    val = lambda k: f[k]["value"] if f.get(k) else None  # noqa: E731
    ref = norm_ref(val("reference_no"))
    rec, by = None, None
    for r in records:
        if r.get("sha256") and r["sha256"] == sha:
            rec, by = r, "sha256"
            break
    if not rec and ref:
        rec = next((r for r in records if norm_ref(r["reference_no"]) == ref), None)
        by = "reference_no" if rec else None
    if not rec:
        return {"matched": False, "by": None, "record": None, "diffs": [], "revoked": False}

    diffs: list[dict] = []

    def diff(field, doc, reg, sev):
        diffs.append({"field": field, "document": doc, "registry": reg, "severity": sev})

    if by == "sha256" and ref and norm_ref(rec["reference_no"]) != ref:
        diff("reference_no", val("reference_no"), rec["reference_no"], "high")
    inst = val("institute_name")
    if rec.get("institute_name") and inst and SequenceMatcher(None, _alnum(inst), _alnum(rec["institute_name"])).ratio() < 0.75:
        diff("institute_name", inst, rec["institute_name"], "high")
    ay = val("academic_year")
    if rec.get("academic_year") and ay and _alnum(ay) != _alnum(rec["academic_year"]):
        diff("academic_year", ay, rec["academic_year"], "high")
    for key in ("valid_upto", "issue_date"):
        a, b = parse_date(val(key) or ""), parse_date(rec.get(key) or "")
        if a and b and a != b:
            diff(key, str(a), str(b), "medium")
    pid = val("permanent_id")
    if rec.get("permanent_id") and pid and _alnum(pid) != _alnum(rec["permanent_id"]):
        diff("permanent_id", pid, rec["permanent_id"], "medium")
    reg_prog = set().union(*[_prog(c) for c in (rec.get("courses") or [])]) if rec.get("courses") else set()
    doc_prog = set().union(*[_prog(c["text"]) for c in parsed["courses"]]) if parsed["courses"] else set()
    extra = sorted(doc_prog - reg_prog) if reg_prog else []
    if extra:
        diff("programmes", ", ".join(extra), ", ".join(sorted(reg_prog)), "high")
    return {"matched": True, "by": by, "record": {k: rec.get(k) for k in PUBLIC_KEYS}, "diffs": diffs,
            "revoked": rec.get("status") == "revoked", "hash_ok": (rec["sha256"] == sha) if rec.get("sha256") else None}


def _f(fid, sev, title, detail, evidence=None):
    return {"id": fid, "severity": sev, "category": "regulatory", "title": title, "detail": detail, "evidence": evidence}


def regulatory_findings(parsed: dict, match: dict, today: date) -> list[dict]:
    out = []
    for d in match["diffs"]:
        label = {"programmes": "Programme in the letter is not approved in the issuer's record"}.get(
            d["field"], f"{d['field'].replace('_', ' ').capitalize()} differs from the issuer's record")
        out.append({"id": f"mismatch_{d['field']}", "severity": d["severity"], "category": "mismatch", "title": label,
                    "detail": f"Document: {d['document']}  |  Registry: {d['registry']}", "evidence": None})
    if match["revoked"]:
        out.append(_f("revoked", "high", "Issuer has revoked this approval", "The registry record for this reference number is marked revoked."))
    rec = match["record"] or {}
    valid = parse_date(rec.get("valid_upto") or "") or parse_date(
        (parsed["fields"].get("valid_upto") or {}).get("value", "") if parsed["fields"].get("valid_upto") else "")
    if valid and valid < today:
        out.append(_f("expired", "high", "Approval validity has lapsed", f"Valid until {valid}; today is {today}."))
    elif not valid and parsed["academic_year_span"] and parsed["academic_year_span"][0] < current_ay_start(today) - 0:
        out.append(_f("ay_past", "low", "Approval is for a past academic year",
                      f"Academic year {parsed['academic_year_span'][0]}-{parsed['academic_year_span'][1]}; current academic year starts {current_ay_start(today)}. "
                      "Confirm a renewal exists."))
    return out
