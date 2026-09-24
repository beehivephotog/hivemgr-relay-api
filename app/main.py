"""HiveMGR Relay -- standalone service.

Two jobs, one small app:
1. Relay artwork-approval customer responses back to each shop's local install via
   outbound polling (the shop calls out; this service never reaches into a shop's LAN).
2. Validate each shop's license/serial.

See README.md for the sync protocol and schema.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routes import public, shop

app = FastAPI(title="HiveMGR Relay", version="1.0.0")
app.include_router(shop.router)
app.include_router(public.router)


@app.get("/health")
def health():
    return {"ok": True, "service": "hivemgr-relay"}


@app.get("/")
def root():
    return {"service": "hivemgr-relay", "docs": "/docs"}


@app.exception_handler(KeyError)
def missing_env_handler(request: Request, exc: KeyError):
    # Surfaces a misconfigured DATABASE_URL etc. as a clean 500 instead of a stack trace.
    return JSONResponse(status_code=500, content={"detail": f"Server misconfigured: missing {exc}"})
