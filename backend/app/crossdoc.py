"""Cross-document consistency: compare this upload with everything already stored (all accounts).
Other accounts' filenames/identities are never included in findings."""
from .parser import parse_date
from .registry import _alnum, norm_ref
from difflib import SequenceMatcher


def _f(fid, sev, title, detail, evidence=None):
    return {"id": fid, "severity": sev, "category": "integrity", "title": title, "detail": detail, "evidence": evidence}


def cross_checks(parsed: dict, sha: str, user_id: str, docs: list[dict]) -> list[dict]:
    out: list[dict] = []
    f = parsed["fields"]
    val = lambda k: f[k]["value"] if f.get(k) else None  # noqa: E731
    ref, inst, ay, valid = norm_ref(val("reference_no")), _alnum(val("institute_name")), _alnum(val("academic_year")), val("valid_upto")

    same = [d for d in docs if d["sha256"] == sha]
    mine = [d for d in same if d["user_id"] == user_id]
    others = [d for d in same if d["user_id"] != user_id]
    if mine:
        out.append(_f("dup_file", "info", "Identical file analysed before", f"Same SHA-256 as '{mine[0]['filename']}' ({mine[0]['created_at'][:10]})."))
    if others:
        out.append(_f("dup_other", "low", "Identical file submitted by other accounts",
                      f"{len(others)} other submission(s) of this exact file exist. Not wrong by itself (shared letters are common)."))
    if not ref:
        return out
    related = [d for d in docs if d["sha256"] != sha and norm_ref(d.get("reference_no")) == ref]
    other_inst = {_alnum(d["institute_name"]) for d in related if d.get("institute_name") and inst
                  and SequenceMatcher(None, inst, _alnum(d["institute_name"])).ratio() < 0.6}
    if other_inst:
        out.append(_f("ref_reuse", "high" if len(other_inst) > 1 else "medium", "Reference number seen with a different institution",
                      f"{len(related)} stored document(s) carry this reference number; {len(other_inst)} name a different institution.", val("reference_no")))
    ay_diff = {d["academic_year"] for d in related if d.get("academic_year") and ay and _alnum(d["academic_year"]) != ay}
    if ay_diff:
        out.append(_f("ref_ay_conflict", "medium", "Same reference number, different academic year in another document",
                      f"This letter says {val('academic_year')}; other stored copies say {', '.join(sorted(ay_diff))}.", val("reference_no")))
    mine_valid = parse_date(valid or "")
    vd = {d["valid_upto"] for d in related if d.get("valid_upto") and mine_valid and parse_date(d["valid_upto"]) and parse_date(d["valid_upto"]) != mine_valid}
    if vd:
        out.append(_f("ref_valid_conflict", "medium", "Same reference number, different validity date in another document",
                      f"This letter says {mine_valid}; other stored copies say {', '.join(sorted(vd))}.", val("reference_no")))
    return out
