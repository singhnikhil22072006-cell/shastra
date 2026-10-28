import { useCallback, useEffect, useState } from "react";
import { getJSON, publicJSON, send } from "../api";
import { Err } from "./shared.jsx";
import { Card, COLORS, Gauge, Modal, VERDICT_COLOR, VerdictBadge, fmtDate } from "./ui.jsx";

const STATE_COLOR = { ACTIVE: COLORS.lime, REVOKED: COLORS.red, EXPIRED: COLORS.orange };
const shareUrl = (token) => `${location.origin}${location.pathname}?share=${token}`;

/** Look a reference number up in the issuers' registries without uploading anything. */
export function Lookup() {
  const [ref, setRef] = useState(""), [res, setRes] = useState(null), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  async function go(e) {
    e.preventDefault(); setBusy(true); setErr(""); setRes(null);
    try { setRes(await getJSON(`/api/lookup?ref=${encodeURIComponent(ref.trim())}`)); } catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  return (
    <div className="grid" style={{ maxWidth: 760 }}>
      <Card>
        <h3 style={{ marginTop: 0 }}>Quick reference lookup</h3>
        <p className="muted small">Check a letter's reference number against the issuing organizations' registries — no upload needed. Enter the full number exactly as printed on the letter.</p>
        <form onSubmit={go} className="row" style={{ flexWrap: "nowrap" }}>
          <input aria-label="Reference number" required minLength={5} placeholder="Western/1-12345/2026/EOA" value={ref} onChange={(e) => setRef(e.target.value)} />
          <button disabled={busy}>{busy ? "Searching…" : "Look up"}</button>
        </form>
      </Card>
      <Err msg={err} />
      {res && !res.found && <Card className="pink"><h4 style={{ marginTop: 0 }}>No registry record</h4>
        <p>No approved issuer has registered this reference number. That is <b>not proof of forgery</b> — the issuer may simply not use SHASTRA. Upload the letter to run the full authenticity checks.</p></Card>}
      {res?.records.map((r, i) => (
        <Card key={i} style={{ "--c": STATE_COLOR[r.state] }}>
          <div className="row between"><span className="mono">{r.reference_no}</span><span className="badge" style={{ "--c": STATE_COLOR[r.state] }}>{r.state}</span></div>
          <h4 style={{ margin: ".6rem 0 .2rem" }}>{r.institute_name}</h4>
          <p className="small muted" style={{ margin: 0 }}>Academic year {r.academic_year || "—"} · valid up to {r.valid_upto || "—"} · issued by {r.issuer}</p>
          {r.courses.length > 0 && <p className="small">Approved programmes: {r.courses.join(", ")}</p>}
        </Card>))}
    </div>
  );
}

/** Create / copy / revoke expiring public links to an identity-free copy of a verdict. */
export function ShareModal({ doc, onClose }) {
  const [links, setLinks] = useState([]), [days, setDays] = useState(7), [err, setErr] = useState(""), [copied, setCopied] = useState("");
  const load = useCallback(async () => { try { setLinks(await getJSON(`/api/documents/${doc.id}/shares`)); } catch (e) { setErr(e.message); } }, [doc.id]);
  useEffect(() => { load(); }, [load]);
  const act = (fn) => async (...a) => { setErr(""); try { await fn(...a); await load(); } catch (e) { setErr(e.message); } };
  const create = act(() => send("POST", `/api/documents/${doc.id}/share`, { days: Number(days) }));
  const revoke = act((l) => send("DELETE", `/api/shares/${l.id}`));
  async function copy(l) { try { await navigator.clipboard.writeText(shareUrl(l.token)); setCopied(l.id); setTimeout(() => setCopied(""), 1500); } catch { setErr("Copy failed — select the link manually."); } }
  return (
    <Modal title="Share verification result" onClose={onClose}>
      <p className="small muted">Anyone with the link can see the verdict, signals and findings — <b>not</b> your file, file name or e-mail. It is a snapshot: re-verifying later does not change it. Revoke any time.</p>
      <div className="row"><label style={{ margin: 0 }}>Expires after
        <select value={days} onChange={(e) => setDays(e.target.value)} style={{ width: "auto", marginLeft: ".5rem" }}>{[1, 7, 30, 90].map((d) => <option key={d} value={d}>{d} day{d > 1 ? "s" : ""}</option>)}</select></label>
        <button onClick={create}>Create link</button></div>
      <Err msg={err} />
      <ul className="docs" style={{ maxHeight: "30vh" }}>
        {links.length === 0 && <li className="muted small">No links yet.</li>}
        {links.map((l) => (
          <li key={l.id} style={{ flexDirection: "column", alignItems: "stretch", opacity: l.live ? 1 : 0.5 }}>
            <input readOnly aria-label="Share link" value={shareUrl(l.token)} onFocus={(e) => e.target.select()} className="mono small" />
            <div className="row between"><span className="small muted">{l.live ? `expires ${fmtDate(l.expires_at)}` : l.revoked ? "revoked" : "expired"} · {l.views} view(s)</span>
              <span className="row">{l.live && <button className="sm ghost" onClick={() => copy(l)}>{copied === l.id ? "Copied ✔" : "Copy"}</button>}
                {l.live && <button className="sm danger" onClick={() => revoke(l)}>Revoke</button>}</span></div>
          </li>))}
      </ul>
    </Modal>
  );
}

const REVIEW = { flagged: COLORS.red, under_review: COLORS.amber, resolved: COLORS.lime, dismissed: COLORS.slate };

/** Org/admin triage: set the review status and keep an internal note trail (users never see the notes). */
export function ReviewPanel({ doc, base, onChanged }) {
  const [status, setStatus] = useState(doc.review_status === "clear" || doc.review_status === "published" ? "under_review" : doc.review_status);
  const [note, setNote] = useState(""), [notes, setNotes] = useState(doc.review_notes || []), [current, setCurrent] = useState(doc.review_status), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => { setNotes(doc.review_notes || []); setCurrent(doc.review_status); }, [doc.id, doc.review_notes, doc.review_status]);
  async function go(e) {
    e.preventDefault(); setBusy(true); setErr("");
    try { const r = await send("POST", `${base}/${doc.id}/review`, { status, note }); setNotes(r.review_notes); setCurrent(r.review_status); setNote(""); onChanged?.(); }
    catch (x) { setErr(x.message); } finally { setBusy(false); }
  }
  return (
    <Card>
      <div className="row between"><h3 style={{ margin: 0 }}>Review</h3><span className="badge" style={{ "--c": REVIEW[current] || COLORS.cyan }}>{current}</span></div>
      <p className="small muted">Internal to organization reviewers and admins. The uploader sees only the status.</p>
      <form onSubmit={go}>
        <div className="grid g2" style={{ gap: "0 1rem" }}>
          <label>Set status<select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="flagged">flagged</option><option value="under_review">under review</option><option value="resolved">resolved</option><option value="dismissed">dismissed (false alarm)</option></select></label>
          <label>Note<input maxLength={1000} placeholder="What did you check / decide?" value={note} onChange={(e) => setNote(e.target.value)} /></label>
        </div>
        <Err msg={err} /><button disabled={busy}>{busy ? "Saving…" : "Save review"}</button>
      </form>
      {notes.length > 0 && <ul className="small" style={{ paddingLeft: "1.1rem" }}>{[...notes].reverse().map((n, i) =>
        <li key={i}><b style={{ color: REVIEW[n.status] }}>{n.status}</b> · {n.by} ({n.role}) · <span className="muted">{fmtDate(n.at)}</span>{n.note && <> — {n.note}</>}</li>)}</ul>}
    </Card>
  );
}

/** Registry records whose approval lapses soon. */
export function ExpiryCard({ registry }) {
  const rows = registry?.expiring_soon || [];
  return (
    <Card className={rows.length ? "pink" : ""}>
      <h3 style={{ marginTop: 0 }}>Approvals expiring within {registry?.window_days ?? 60} days</h3>
      {registry?.expired_active > 0 && <p className="notice error">{registry.expired_active} active record(s) are already past their valid-up-to date.</p>}
      {rows.length === 0 ? <p className="muted">Nothing expiring soon.</p>
        : <table><thead><tr><th>Reference</th><th>Institute</th><th>Valid up to</th><th>Days left</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.id}><td className="mono">{r.reference_no}</td><td>{r.institute_name}</td><td>{r.valid_upto}</td>
            <td><span className="badge" style={{ "--c": r.days_left <= 14 ? COLORS.red : COLORS.amber }}>{r.days_left}</span></td></tr>)}</tbody></table>}
    </Card>
  );
}

/** Public page behind /?share=TOKEN. No sign-in; shows only the identity-free snapshot. */
export function PublicShare({ token }) {
  const [data, setData] = useState(null), [err, setErr] = useState("");
  useEffect(() => { publicJSON(`/api/public/share/${encodeURIComponent(token)}`).then(setData).catch((e) => setErr(e.message)); }, [token]);
  if (err) return <main className="page"><p className="notice error" role="alert">{err}</p><a href={location.pathname}>Go to SHASTRA</a></main>;
  if (!data) return <p className="mono" style={{ textAlign: "center", marginTop: "30vh" }}>&gt; FETCHING SHARED RESULT…</p>;
  const s = data.snapshot, vc = VERDICT_COLOR[s.verdict];
  return (
    <main className="page" style={{ maxWidth: 900 }}>
      <header className="top"><div className="brand"><span className="glitch" data-text="SHASTRA">SHASTRA</span><span className="chip">shared result</span></div></header>
      <Card className="hero-v" style={{ "--c": vc }}>
        <div>
          <div className="muted small mono">&gt; VERIFICATION VERDICT</div>
          <div className="big">{s.verdict}</div>
          <p>{s.summary}</p>
          <p className="small mono muted" style={{ margin: 0 }}>{s.reference_no || "no reference"} · {s.institute_name || "unknown institute"} · {s.academic_year || "—"}</p>
        </div>
        <Gauge value={s.trust_score} color={vc} />
      </Card>
      <div className="grid g2" style={{ marginTop: "1rem" }}>
        <Card><h3 style={{ marginTop: 0 }}>Signals</h3><ul className="small">{s.signals.map((x, i) => <li key={i}><b>{x.label}</b> — {x.state}</li>)}</ul></Card>
        <Card className="pink"><h3 style={{ marginTop: 0 }}>Findings</h3>
          {s.mismatches?.map((m, i) => <p key={i} className="small"><b>{m.field}</b>: <span className="mono">{m.document}</span> ≠ <span className="mono">{m.registry}</span></p>)}
          {s.findings.length === 0 ? <p className="muted small">No high or medium findings.</p> : <ul className="small">{s.findings.map((f, i) => <li key={i}><b>{f.severity}</b> {f.title}</li>)}</ul>}</Card>
      </div>
      <p className="note-box">Snapshot taken {fmtDate(data.shared_at)}; link expires {fmtDate(data.expires_at)}. The verdict compares the letter with the issuing organization's registry; it is not a live AICTE query and may have changed since.</p>
    </main>
  );
}
