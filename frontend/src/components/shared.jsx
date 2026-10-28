import { useState } from "react";
import { Card, COLORS, HBars, Modal, RiskBadge, SEV_COLOR, Stat, Timeline, VERDICT_COLOR, VerdictBadge, Donut, fmtDate } from "./ui.jsx";

export function Tabs({ tabs, value, onChange }) {
  return <nav className="tabs" role="tablist">{tabs.map(([id, label]) => <button key={id} role="tab" aria-selected={value === id} className={value === id ? "on" : ""} onClick={() => onChange(id)}>{label}</button>)}</nav>;
}

export function Err({ msg }) { return msg ? <p className="notice error" role="alert">{msg}</p> : null; }

/** Verdict / category / timeline charts shared by all three dashboards. */
export function Analytics({ s }) {
  if (!s) return <p className="mono muted">&gt; LOADING TELEMETRY…</p>;
  return (
    <div className="grid">
      <div className="grid g4">
        <Stat k="Documents analysed" v={s.total} />
        <Stat k="Verified" v={s.verified} color={COLORS.lime} />
        <Stat k="Flagged" v={s.flagged} color={COLORS.red} sub="mismatch + suspicious" />
        <Stat k="Avg trust score" v={s.avg_trust} color={COLORS.violet} />
      </div>
      <div className="grid g2">
        <Card><h3 style={{ marginTop: 0 }}>Verdict distribution</h3><Donut data={s.by_verdict} colorMap={VERDICT_COLOR} /></Card>
        <Card className="pink"><h3 style={{ marginTop: 0 }}>Findings by category</h3><HBars data={s.by_category} /></Card>
      </div>
      <div className="grid g2">
        <Card><h3 style={{ marginTop: 0 }}>Activity · last 14 days</h3><Timeline points={s.timeline} /></Card>
        <Card><h3 style={{ marginTop: 0 }}>Findings by severity</h3><HBars data={s.by_severity} colorMap={SEV_COLOR} /></Card>
      </div>
      {s.top_institutes?.length > 0 && <Card><h3 style={{ marginTop: 0 }}>Most-flagged institutes</h3>
        <HBars data={Object.fromEntries(s.top_institutes.map((x) => [`${x.name} (${x.flagged}/${x.total})`, x.flagged]))}
          colorMap={Object.fromEntries(s.top_institutes.map((x) => [`${x.name} (${x.flagged}/${x.total})`, COLORS.red]))} /></Card>}
    </div>
  );
}

export function DocTable({ rows, onOpen, extra }) {
  if (!rows.length) return <p className="muted">Nothing here yet.</p>;
  return (
    <Card className="scroll-x"><table>
      <thead><tr><th>Reference</th><th>Institute</th><th>Verdict</th><th>Trust</th><th>Risk</th><th>Status</th><th>When</th><th /></tr></thead>
      <tbody>{rows.map((d) => (
        <tr key={d.id}>
          <td className="mono">{d.reference_no || d.filename || "—"}</td><td>{d.institute_name || "—"}</td>
          <td><VerdictBadge v={d.verification_status || "UNVERIFIED"} /></td><td className="mono">{d.trust_score ?? "—"}</td>
          <td><RiskBadge v={d.risk_level} /></td><td className="small">{d.review_status}</td><td className="small muted">{fmtDate(d.created_at)}</td>
          <td className="row"><button className="sm ghost" onClick={() => onOpen(d.id)}>Open</button>{extra?.(d)}</td>
        </tr>))}</tbody>
    </table></Card>
  );
}

export function PublishModal({ onClose, onSubmit, defaultTitle, scopes = ["public", "org"] }) {
  const [title, setTitle] = useState(defaultTitle || ""), [note, setNote] = useState(""), [scope, setScope] = useState(scopes[0]), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  async function go(e) { e.preventDefault(); setBusy(true); setErr(""); try { await onSubmit({ title, note, scope }); onClose(); } catch (x) { setErr(x.message); setBusy(false); } }
  return (
    <Modal title="Publish verification report" onClose={onClose}>
      <form onSubmit={go}>
        <label>Title<input required maxLength={160} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
        <label>Note for readers<textarea rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <label>Audience<select value={scope} onChange={(e) => setScope(e.target.value)}>
          {scopes.includes("public") && <option value="public">Public — every signed-in user</option>}
          {scopes.includes("org") && <option value="org">Organization only</option>}</select></label>
        <p className="small muted">Only the verdict, mismatches and findings are published. The uploader's identity and the file itself are never included.</p>
        <Err msg={err} />
        <div className="row"><button className="pink" disabled={busy}>{busy ? "Publishing…" : "Publish"}</button><button type="button" className="ghost" onClick={onClose}>Cancel</button></div>
      </form>
    </Modal>
  );
}

/** Published-report ledger. `onWithdraw` only for admins. */
export function Reports({ rows, onWithdraw }) {
  if (!rows.length) return <p className="muted">No published reports.</p>;
  return (
    <div className="grid g2">{rows.map((r) => {
      const s = r.snapshot, sev = s.findings.reduce((a, f) => ({ ...a, [f.severity]: (a[f.severity] || 0) + 1 }), {});
      return (
        <Card key={r.id} className={s.verdict === "VERIFIED" ? "" : "pink"} style={{ opacity: r.status === "withdrawn" ? 0.5 : 1 }}>
          <div className="row between"><VerdictBadge v={s.verdict} /><span className="small muted mono">{fmtDate(r.created_at)} · {r.scope}{r.status === "withdrawn" ? " · WITHDRAWN" : ""}</span></div>
          <h4 style={{ margin: ".7rem 0 .2rem" }}>{r.title}</h4>
          <p className="small mono muted" style={{ margin: 0 }}>{s.reference_no || "no reference"} · {s.institute_name || "unknown institute"} · {s.academic_year || "—"}</p>
          {r.note && <p>{r.note}</p>}
          <div className="grid g2" style={{ gridTemplateColumns: "auto 1fr", alignItems: "center" }}><Donut data={sev} colorMap={SEV_COLOR} size={110} center={`${s.trust_score}`} />
            <div>{s.mismatches?.map((m, i) => <p key={i} className="small" style={{ margin: ".15rem 0" }}><b>{m.field}</b>: <span className="mono">{m.document}</span> ≠ <span className="mono">{m.registry}</span></p>)}</div></div>
          <ul className="small" style={{ paddingLeft: "1.1rem" }}>{s.findings.slice(0, 5).map((f, i) => <li key={i}><b style={{ color: SEV_COLOR[f.severity] }}>{f.severity}</b> {f.title}</li>)}</ul>
          <p className="small muted">by {r.published_by_email}</p>
          {onWithdraw && <button className="sm danger" onClick={() => onWithdraw(r)}>{r.status === "published" ? "Withdraw" : "Re-publish"}</button>}
        </Card>);
    })}</div>
  );
}
