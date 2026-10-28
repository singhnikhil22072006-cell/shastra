from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes import admin_r, org_r, public_r, user_r

app = FastAPI(title="SHASTRA API", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin],
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/health")
def health():
    return {"ok": True}


for r in (user_r, org_r, admin_r, public_r):
    app.include_router(r)
