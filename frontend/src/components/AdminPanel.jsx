import { useCallback, useEffect, useState } from "react";
import { downloadFile, getJSON, send } from "../api";
import Result from "./Result.jsx";
import { ReviewPanel } from "./features.jsx";
import { Analytics, DocTable, Err, PublishModal, Reports, Tabs } from "./shared.jsx";
import Duplicates from "./Duplicates.jsx";
import { Card, COLORS, Donut, Stat, fmtDate } from "./ui.jsx";

export default function AdminPanel({ me }) {
  const [tab, setTab] = useState("overview");
  const [d, setD] = useState({ stats: null, docs: [], orgs: [], users: [], reports: [], audit: [] });
  const [current, setCurrent] = useState(null), [publishing, setPublishing] = useState(false), [filter, setFilter] = useState("all");
  const [error, setError] = useState(""), [info, setInfo] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [stats, docs, orgs, users, reports, audit] = await Promise.all(["stats", "documents", "orgs", "users", "reports", "audit"].map((k) => getJSON(`/api/admin/${k}`)));
      setD({ stats, docs, orgs, users, reports, audit });
    } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  const run = (fn) => async (...a) => { setError(""); setInfo(""); try { await fn(...a); await refresh(); } catch (e) { setError(e.message); } };

  const open = run(async (id) => { setCurrent(await getJSON(`/api/admin/documents/${id}`)); setTab("documents"); });
  const org = run((o, status) => send("PATCH", `/api/admin/orgs/${o.id}`, { status }));
  const user = run((u, patch) => send("PATCH", `/api/admin/users/${u.id}`, patch));
  const withdraw = run((r) => send("PATCH", `/api/admin/reports/${r.id}`, { status: r.status === "published" ? "withdrawn" : "published" }));
  const s = d.stats, pendingOrgs = d.orgs.filter((o) => o.status === "pending").length;
  const shown = d.docs.filter((x) => filter === "all" ? true : filter === "flagged" ? ["MISMATCH", "SUSPICIOUS"].includes(x.verification_status) : x.verification_status === filter);
  const orgName = (id) => d.orgs.find((o) => o.id === id)?.name || id?.slice(0, 8);

  return (
    <>
      <Tabs value={tab} onChange={(t) => { setTab(t); setCurrent(null); }} tabs={[["overview", "Command center"], ["documents", `Documents (${d.docs.length})`], ["duplicates", "Duplicates"], ["orgs", `Organizations${pendingOrgs ? ` · ${pendingOrgs} pending` : ""}`], ["users", `Users (${d.users.length})`], ["reports", `Reports (${d.reports.length})`], ["audit", "Audit log"]]} />
      <main className="page">
        <Err msg={error} />{info && <p className="notice">{info}</p>}

        {tab === "overview" && s && <div className="grid">
          <div className="grid g4">
            <Stat k="Users" v={s.users.user} color={COLORS.cyan} /><Stat k="Organizations (approved)" v={s.orgs.approved} color={COLORS.amber} sub={`${s.orgs.pending} pending`} />
            <Stat k="Reports published" v={s.reports.published} color={COLORS.pink} sub={`${s.reports.withdrawn} withdrawn`} /><Stat k="Admins" v={s.users.admin} color={COLORS.violet} />
          </div>
          <Analytics s={s} />
          <div className="grid g2"><Card><h3 style={{ marginTop: 0 }}>Organizations by status</h3><Donut data={s.orgs} colorMap={{ approved: COLORS.lime, pending: COLORS.amber, suspended: COLORS.red }} /></Card>
            <Card><h3 style={{ marginTop: 0 }}>Accounts by role</h3><Donut data={s.users} colorMap={{ user: COLORS.cyan, org: COLORS.amber, admin: COLORS.pink }} /></Card></div>
        </div>}

        {tab === "documents" && (current
          ? <><button className="ghost sm" onClick={() => setCurrent(null)} style={{ marginBottom: "1rem" }}>← All documents</button>
              <Result doc={current} actions={<><button className="pink" onClick={() => setPublishing(true)}>Publish report</button>
                <button className="ghost" onClick={run(() => downloadFile(`/api/admin/documents/${current.id}/report.pdf`, `shastra-${current.id.slice(0, 8)}.pdf`))}>PDF</button></>} />
              <div style={{ marginTop: "1rem" }}><ReviewPanel doc={current} base="/api/admin/documents" onChanged={refresh} /></div>
              {publishing && <PublishModal defaultTitle={`Verification report ${current.reference_no || ""}`} onClose={() => setPublishing(false)} onSubmit={async (b) => { await send("POST", `/api/admin/documents/${current.id}/publish`, b); setInfo("Report published."); refresh(); }} />}</>
          : <><div className="row" style={{ marginBottom: "1rem" }}><button className="sm pink" onClick={run(() => downloadFile("/api/admin/documents/export.csv", "shastra-all-documents.csv"))}>Export CSV</button>{["all", "flagged", "VERIFIED", "PARTIAL", "UNVERIFIED", "SUSPICIOUS", "MISMATCH"].map((f) => <button key={f} className={`sm ${filter === f ? "" : "ghost"}`} onClick={() => setFilter(f)}>{f}</button>)}</div>
              <DocTable rows={shown} onOpen={open} extra={(x) => x.org_id && <span className="small muted">{orgName(x.org_id)}</span>} /></>)}

        {tab === "duplicates" && <Duplicates scope="admin" />}
        {tab === "orgs" && <Card className="scroll-x"><table><thead><tr><th>Organization</th><th>Status</th><th>Registered</th><th /></tr></thead><tbody>
          {d.orgs.map((o) => <tr key={o.id}><td>{o.name}</td><td><span className="badge" style={{ "--c": { approved: COLORS.lime, pending: COLORS.amber, suspended: COLORS.red }[o.status] }}>{o.status}</span></td><td className="small muted">{fmtDate(o.created_at)}</td>
            <td className="row">{o.status !== "approved" && <button className="sm" onClick={() => org(o, "approved")}>Approve</button>}{o.status !== "suspended" && <button className="sm danger" onClick={() => org(o, "suspended")}>Suspend</button>}</td></tr>)}</tbody></table></Card>}

        {tab === "users" && <Card className="scroll-x"><table><thead><tr><th>Email</th><th>Role</th><th>Organization</th><th>Status</th><th /></tr></thead><tbody>
          {d.users.map((u) => <tr key={u.id}><td className="mono">{u.email}</td><td><span className={`chip ${u.role}`}>{u.role}</span></td><td>{u.org_id ? orgName(u.org_id) : "—"}</td><td>{u.status}</td>
            <td className="row">{u.id !== me.id && <>
              <select style={{ width: "auto" }} aria-label={`Role for ${u.email}`} value={u.role} onChange={(e) => user(u, { role: e.target.value })}><option>user</option><option>org</option><option>admin</option></select>
              <button className="sm danger" onClick={() => user(u, { status: u.status === "active" ? "suspended" : "active" })}>{u.status === "active" ? "Suspend" : "Reactivate"}</button></>}</td></tr>)}</tbody></table></Card>}

        {tab === "reports" && <Reports rows={d.reports} onWithdraw={withdraw} />}

        {tab === "audit" && <><div className="row" style={{ marginBottom: "1rem" }}><button className="sm pink" onClick={run(() => downloadFile("/api/admin/audit/export.csv", "shastra-audit-log.csv"))}>Export audit log CSV</button></div><Card className="scroll-x"><table><thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Meta</th></tr></thead><tbody>
          {d.audit.map((a) => <tr key={a.id}><td className="small muted">{fmtDate(a.created_at)}</td><td className="mono">{a.actor_email}</td><td>{a.action}</td><td className="mono small">{a.target?.slice(0, 8)}</td><td className="mono small">{JSON.stringify(a.meta)}</td></tr>)}</tbody></table></Card></>}
      </main>
    </>
  );
}
