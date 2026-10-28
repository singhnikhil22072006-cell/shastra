import { useEffect, useState } from "react";
import { getJSON, send } from "../api";
import { Card, COLORS, HBars, Stat, VerdictBadge, fmtDate } from "./ui.jsx";

const LABEL = { repeated_submission: "Repeated submissions", shared_file: "Shared files", new_version: "Different versions", conflict: "Conflicting information" };
const KIND_COLOR = { repeated_submission: COLORS.slate, shared_file: COLORS.cyan, new_version: COLORS.violet, conflict: COLORS.red };

/** scope: "user" | "org" | "admin". All numbers come from the API; nothing is pre-filled. */
export default function Duplicates({ scope }) {
  const [d, setD] = useState(null), [err, setErr] = useState("");
  useEffect(() => { getJSON(scope === "user" ? "/api/duplicates" : `/api/${scope}/duplicates`).then(setD).catch((e) => setErr(e.message)); }, [scope]);
  if (err) return <p className="notice error" role="alert">{err}</p>;
  if (!d) return <p className="mono muted">&gt; LOADING…</p>;
  return (
    <div className="grid">
      <p className="note-box">A repeated file is not fraud. Only groups with conflicting details are marked for review. Matching uses file fingerprints (SHA-256) and the reference number.</p>
      <div className="grid g4">
        <Stat k="Documents processed" v={d.total_documents} />
        <Stat k="Duplicate files" v={d.duplicate_files} color={COLORS.cyan} sub="extra copies of the same file" />
        <Stat k="Conflicts to review" v={d.counts.conflict} color={COLORS.red} />
        <Stat k="Awaiting review" v={d.awaiting_review} color={COLORS.amber} />
      </div>
      <Card><h3 style={{ marginTop: 0 }}>Groups by type</h3><HBars data={Object.fromEntries(Object.entries(d.counts).map(([k, v]) => [LABEL[k], v]))} colorMap={Object.fromEntries(Object.entries(KIND_COLOR).map(([k, c]) => [LABEL[k], c]))} />
        <p className="small muted" style={{ marginBottom: 0 }}>Average verification time: {d.avg_verification_seconds ?? "not measured"}. {d.avg_verification_note}</p></Card>
      {d.groups.length === 0 && <Card><p className="muted" style={{ margin: 0 }}>No duplicate or conflicting groups found in the documents you can see.</p></Card>}
      {d.groups.map((g) => (
        <Card key={g.kind + g.key} className={g.needs_review ? "pink" : ""}>
          <div className="row between"><b style={{ color: KIND_COLOR[g.kind] }}>{LABEL[g.kind]}</b><span className="small muted mono">{g.count} document(s) share this {g.kind === "repeated_submission" || g.kind === "shared_file" ? "file" : "reference"}{g.needs_review ? " · NEEDS REVIEW" : ""}</span></div>
          <p className="small">{g.explanation}{g.differs_in?.length ? ` Differs in: ${g.differs_in.join(", ").replace(/_/g, " ")}.` : ""}</p>
          <ul className="docs">{g.members.map((m) => <li key={m.id}><span className="small">{m.filename || m.reference_no || m.id.slice(0, 8)} · {m.institute_name || "—"} · {m.academic_year || "—"} · <span className="muted">{fmtDate(m.created_at)}</span></span><VerdictBadge v={m.verdict} /></li>)}</ul>
        </Card>))}
      {scope === "admin" && <Impact />}
    </div>
  );
}

function Impact() {
  const [v, setV] = useState(null), [f, setF] = useState({ baseline_duplicate_cases: "", period_label: "", post_start: "", source_note: "" }), [err, setErr] = useState("");
  useEffect(() => { getJSON("/api/admin/impact").then(setV).catch((e) => setErr(e.message)); }, []);
  const save = async (e) => { e.preventDefault(); setErr(""); try { setV(await send("PUT", "/api/admin/impact", { ...f, baseline_duplicate_cases: Number(f.baseline_duplicate_cases) })); } catch (x) { setErr(x.message); } };
  const b = v?.baseline, set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <Card>
      <h3 style={{ marginTop: 0 }}>Impact evaluation: baseline vs measured pilot</h3>
      <p className="small muted">{v?.formula}</p>
      {err && <p className="notice error" role="alert">{err}</p>}
      {!b ? <p className="notice">No baseline recorded yet, so no reduction is shown. Enter the duplicate-case count measured in your pre-deployment process.</p>
        : <div className="grid g4"><Stat k="Baseline duplicate cases" v={b.baseline_duplicate_cases} sub={b.period_label} /><Stat k="Post-deployment duplicates" v={v.post_duplicate_cases} sub={`since ${b.post_start}`} color={COLORS.cyan} /><Stat k="Reduction" v={v.reduction_pct == null ? "—" : `${v.reduction_pct}%`} color={COLORS.lime} sub="measured, not projected" /></div>}
      <form onSubmit={save} style={{ marginTop: "1rem" }}>
        <div className="grid g2">
          <label>Baseline duplicate cases<input type="number" min="1" required value={f.baseline_duplicate_cases} onChange={set("baseline_duplicate_cases")} /></label>
          <label>Baseline period (e.g. "Manual process, Jan–Mar")<input required maxLength={120} value={f.period_label} onChange={set("period_label")} /></label>
          <label>Pilot start date<input type="date" required value={f.post_start} onChange={set("post_start")} /></label>
          <label>Source of baseline figure<input maxLength={500} value={f.source_note} onChange={set("source_note")} /></label>
        </div>
        <button style={{ marginTop: ".6rem" }}>Record baseline</button>
      </form>
    </Card>
  );
}
