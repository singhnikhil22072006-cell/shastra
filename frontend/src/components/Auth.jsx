import { useState } from "react";
import { supabase } from "../supabase";
import { Tilt } from "./ui.jsx";

export default function Auth() {
  const [mode, setMode] = useState("signin");
  const [kind, setKind] = useState("user");
  const [orgName, setOrgName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setMsg("");
    let error;
    if (mode === "signin") ({ error } = await supabase.auth.signInWithPassword({ email, password }));
    else {
      // The role is only a REQUEST. The backend creates a *pending* organization that an admin must approve.
      const data = kind === "org" ? { requested_role: "organization", org_name: orgName } : {};
      ({ error } = await supabase.auth.signUp({ email, password, options: { data } }));
      if (!error) setMsg("Identity created. If e-mail confirmation is on, confirm it, then sign in." + (kind === "org" ? " Your organization stays PENDING until an admin approves it." : ""));
    }
    if (error) setMsg(error.message);
    setBusy(false);
  }

  return (
    <main className="landing">
      <section>
        <div className="tag">&gt; DOCUMENT INTEGRITY GRID // ONLINE_</div>
        <h1 className="glitch" data-text="SHASTRA">SHASTRA</h1>
        <p style={{ fontSize: "1.25rem", maxWidth: "34rem", color: "#b6c8dc" }}>
          Cross-examine AICTE approval letters. Watermarks, signatures, QR codes and forensic traces are checked and matched against what the issuing organization actually registered.
        </p>
        <ul className="feat">
          <li>Issuer-registry matching: field-by-field mismatch detection</li>
          <li>Watermark, digital-signature and QR authenticity signals</li>
          <li>Cross-document conflict detection across all submissions</li>
          <li>Regulatory flags: expired, revoked, unapproved programmes</li>
          <li>Publishable reports with analytics for organizations and admins</li>
        </ul>
        <p><a className="btnlink ghost" href="#/site/home" onClick={() => setTimeout(() => location.reload())}>Platform tour: how it works, architecture, limits</a></p>
      </section>
      <Tilt className="pink" max={5}>
        <h3 style={{ marginTop: 0 }}>{mode === "signin" ? "Authenticate" : "Register identity"}</h3>
        {mode === "signup" && (
          <div className="seg" role="group" aria-label="Account type">
            <button type="button" className={kind === "user" ? "on" : ""} onClick={() => setKind("user")}>User</button>
            <button type="button" className={kind === "org" ? "on" : ""} onClick={() => setKind("org")}>Organization</button>
          </div>
        )}
        <form onSubmit={submit}>
          {mode === "signup" && kind === "org" && <label>Organization name<input required maxLength={120} value={orgName} onChange={(e) => setOrgName(e.target.value)} /></label>}
          <label>Email<input type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>Password<input type="password" required minLength={8} autoComplete={mode === "signin" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} /></label>
          <button disabled={busy}>{busy ? "Working…" : mode === "signin" ? "Enter the grid" : "Create identity"}</button>
        </form>
        {msg && <p className="notice" style={{ marginTop: "1rem" }}>{msg}</p>}
        <p><button className="link" onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setMsg(""); }}>
          {mode === "signin" ? "No identity yet? Register" : "Have an identity? Authenticate"}</button></p>
      </Tilt>
    </main>
  );
}
