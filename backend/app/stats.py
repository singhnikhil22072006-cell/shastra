"""Aggregations for the dashboards. Computed in Python from summary rows (fine up to a few thousand documents;
move to SQL views/RPC beyond that)."""
from collections import Counter
from datetime import date, timedelta


def finding_counts(findings: list[dict]) -> dict:
    return {"category": dict(Counter(f["category"] for f in findings if f["severity"] != "info")),
            "severity": dict(Counter(f["severity"] for f in findings))}


def summarize(rows: list[dict], days: int = 14) -> dict:
    verdict = Counter(r.get("verification_status") or "UNVERIFIED" for r in rows)
    risk = Counter(r.get("risk_level") or "LOW" for r in rows)
    cat, sev = Counter(), Counter()
    for r in rows:
        fc = r.get("finding_counts") or {}
        cat.update(fc.get("category", {}))
        sev.update(fc.get("severity", {}))
    today = date.today()
    line = {(today - timedelta(days=i)).isoformat(): [0, 0] for i in range(days - 1, -1, -1)}
    for r in rows:
        d = (r.get("created_at") or "")[:10]
        if d in line:
            line[d][0] += 1
            line[d][1] += r.get("verification_status") in ("MISMATCH", "SUSPICIOUS")
    tot, bad = Counter(), Counter()
    for r in rows:
        name = (r.get("institute_name") or "").strip()
        if name:
            tot[name] += 1
            bad[name] += r.get("verification_status") in ("MISMATCH", "SUSPICIOUS")
    top = [{"name": n, "flagged": c, "total": tot[n]} for n, c in bad.most_common(5) if c]
    trust = [r["trust_score"] for r in rows if r.get("trust_score") is not None]
    return {"total": len(rows), "flagged": verdict["MISMATCH"] + verdict["SUSPICIOUS"], "verified": verdict["VERIFIED"],
            "avg_trust": round(sum(trust) / len(trust)) if trust else None,
            "by_verdict": dict(verdict), "by_risk": dict(risk), "by_category": dict(cat), "by_severity": dict(sev), "top_institutes": top,
            "timeline": [{"date": d, "documents": v[0], "flagged": v[1]} for d, v in line.items()]}
