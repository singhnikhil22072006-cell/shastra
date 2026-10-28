import { supabase } from "./supabase";

const BASE = import.meta.env.VITE_API_URL;

export async function api(path, options = {}) {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  const headers = { ...(options.headers || {}), Authorization: `Bearer ${token}` };
  let body = options.body;
  if (body && !(body instanceof FormData) && typeof body !== "string") { body = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  const res = await fetch(BASE + path, { ...options, headers, body });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : msg; } catch { /* non-JSON error */ }
    throw new Error(msg);
  }
  return res;
}
export const getJSON = async (path, options) => (await api(path, options)).json();
export const send = (method, path, body) => getJSON(path, { method, body });

export async function downloadFile(path, name) {
  const blob = await (await api(path)).blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}
export const downloadPDF = downloadFile; // same blob download works for PDF and CSV

/** Unauthenticated GET, used only by the public share-link page. */
export async function publicJSON(path) {
  const res = await fetch(BASE + path);
  if (!res.ok) { let m = res.statusText; try { const j = await res.json(); if (typeof j.detail === "string") m = j.detail; } catch { /* non-JSON */ } throw new Error(m); }
  return res.json();
}
