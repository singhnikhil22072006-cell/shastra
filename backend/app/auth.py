"""Authentication + role resolution.

Identity comes from Supabase Auth (token validated server-side). The ROLE comes from our own
`profiles` table, never from anything the browser sends. Signing up as an organization only creates a
*pending* organization; an admin must approve it before any org feature works.
"""
from fastapi import Depends, Header, HTTPException

from .config import settings
from .db import sb


def current_user(authorization: str = Header(default="")) -> dict:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization[7:].strip()
    try:
        user = sb.auth.get_user(token).user
    except Exception:
        raise HTTPException(401, "Invalid or expired session")
    if not user:
        raise HTTPException(401, "Invalid or expired session")
    return {"id": user.id, "email": user.email,
            "confirmed": bool(getattr(user, "email_confirmed_at", None)),
            "meta": dict(getattr(user, "user_metadata", None) or {})}


def current_profile(user: dict = Depends(current_user)) -> dict:
    rows = sb.table("profiles").select("*").eq("id", user["id"]).limit(1).execute().data
    is_admin_mail = (user["email"] or "").lower() in settings.admin_list and user["confirmed"]
    if rows:
        p = rows[0]
        if is_admin_mail and p["role"] != "admin":
            sb.table("profiles").update({"role": "admin"}).eq("id", user["id"]).execute()
            p["role"] = "admin"
    else:
        role, org_id = "user", None
        meta = user["meta"]
        if is_admin_mail:
            role = "admin"
        elif meta.get("requested_role") == "organization" and str(meta.get("org_name", "")).strip():
            org = sb.table("organizations").insert({
                "name": str(meta["org_name"]).strip()[:120], "status": "pending", "created_by": user["id"],
            }).execute().data[0]
            role, org_id = "org", org["id"]
        p = {"id": user["id"], "email": user["email"], "role": role, "org_id": org_id, "status": "active"}
        sb.table("profiles").insert(p).execute()
    if p.get("status") == "suspended":
        raise HTTPException(403, "This account is suspended")
    return {**user, "role": p["role"], "org_id": p.get("org_id")}


def require(*roles: str):
    def dep(p: dict = Depends(current_profile)) -> dict:
        if p["role"] not in roles:
            raise HTTPException(403, "Not allowed for your role")
        return p
    return dep


def require_org(p: dict = Depends(require("org"))) -> dict:
    """Organization endpoints: the org must exist AND be approved by an admin."""
    rows = sb.table("organizations").select("*").eq("id", p["org_id"]).limit(1).execute().data if p["org_id"] else []
    if not rows:
        raise HTTPException(403, "No organization is linked to this account")
    if rows[0]["status"] != "approved":
        raise HTTPException(403, f"Organization is {rows[0]['status']}. An admin must approve it first.")
    return {**p, "org": rows[0]}


def audit(actor: dict, action: str, target: str | None = None, meta: dict | None = None) -> None:
    try:
        sb.table("audit_log").insert({"actor_id": actor["id"], "actor_email": actor["email"], "action": action,
                                      "target": target, "meta": meta or {}}).execute()
    except Exception:  # auditing must never break the request
        pass
