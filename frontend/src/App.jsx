import { lazy, Suspense, useEffect, useState } from "react";
import { supabase } from "./supabase";
import { getJSON } from "./api";
const Scene3D = lazy(() => import("./components/Scene3D.jsx")); // keeps three.js out of the first paint
import Auth from "./components/Auth.jsx";
import UserPanel from "./components/UserPanel.jsx";
import OrgPanel from "./components/OrgPanel.jsx";
import AdminPanel from "./components/AdminPanel.jsx";
import Site from "./components/Site.jsx";
import { PublicShare } from "./components/features.jsx";

/** /?share=TOKEN is a public, sign-in-free page that shows one shared verdict. */
export default function App() {
  const token = new URLSearchParams(location.search).get("share");
  if (location.hash.startsWith("#/site")) return <><Suspense fallback={null}><Scene3D landing /></Suspense><div className="atmos" /><div className="app"><Site /></div></>;
  return token
    ? <><Suspense fallback={null}><Scene3D landing /></Suspense><div className="atmos" /><div className="app"><PublicShare token={token} /></div></>
    : <Main />;
}

function Main() {
  const [session, setSession] = useState(undefined);
  const [me, setMe] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    setMe(null); setError("");
    if (session) getJSON("/api/me").then(setMe).catch((e) => setError(e.message));
  }, [session]);

  let body;
  if (session === undefined) body = <p className="mono" style={{ textAlign: "center", marginTop: "30vh" }}>&gt; INITIALISING GRID…</p>;
  else if (!session) body = <Auth />;
  else if (error) body = <div className="page"><p className="notice error" role="alert">{error}</p><button className="ghost" onClick={() => supabase.auth.signOut()}>Sign out</button></div>;
  else if (!me) body = <p className="mono" style={{ textAlign: "center", marginTop: "30vh" }}>&gt; RESOLVING CLEARANCE…</p>;
  else {
    const Panel = { admin: AdminPanel, org: OrgPanel, user: UserPanel }[me.role] || UserPanel;
    body = (
      <>
        <header className="top">
          <div className="brand"><span className="glitch" data-text="SHASTRA">SHASTRA</span><span className={`chip ${me.role}`}>{me.role === "org" ? "organization" : me.role}</span></div>
          <div className="row"><span className="muted small mono">{me.email}{me.org ? ` · ${me.org.name}` : ""}</span><a className="ghost sm btnlink" href="#/site/home" onClick={() => setTimeout(() => location.reload())}>About</a><button className="ghost sm" onClick={() => supabase.auth.signOut()}>Sign out</button></div>
        </header>
        <Panel me={me} />
      </>
    );
  }
  return <><Suspense fallback={null}><Scene3D landing={!session} /></Suspense><div className="atmos" /><div className="app">{body}</div></>;
}
