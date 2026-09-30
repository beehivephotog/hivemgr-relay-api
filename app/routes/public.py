"""The customer-facing approval page. No login, no account -- the token in the URL
is the only credential. Shows order number, a customer-safe line-item summary, the
shop's name, and (if the shop sent one) the artwork proof itself -- no pricing, no
internal notes, and nothing beyond what that one line item's request carries."""
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from app.deps import get_store
from app.rate_limit import rate_limit_ip
from app.store import Store

router = APIRouter(tags=["public"])
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _view_state(req) -> str:
    if req is None:
        return "not_found"
    if req.status == "responded":
        return "responded"
    if req.is_expired:
        return "expired"
    return "pending"


@router.get("/approve/{token}", response_class=HTMLResponse)
def view_approval(token: str, request: Request, store: Store = Depends(get_store)):
    req = store.get_approval_by_token(token)
    return templates.TemplateResponse(
        request, "approve.html", {"req": req, "state": _view_state(req), "error": None})


@router.post("/approve/{token}", response_class=HTMLResponse)
def submit_approval(token: str, request: Request, response: str = Form(...), comment: str = Form(""),
                    store: Store = Depends(get_store)):
    rate_limit_ip(request)
    error = None
    if response not in ("approved", "changes_requested"):
        error = "Choose one of the two options below."
        req = store.get_approval_by_token(token)
    else:
        req = store.record_response(token, response, comment.strip()[:4000])
    return templates.TemplateResponse(
        request, "approve.html", {"req": req, "state": _view_state(req), "error": error})


@router.get("/approve/{token}/artwork")
def view_artwork(token: str, request: Request, store: Store = Depends(get_store)):
    rate_limit_ip(request, max_requests=30)  # a page load plus the odd reload/retry, not form submissions
    art = store.get_artwork_by_token(token)
    if not art:
        raise HTTPException(status_code=404, detail="No artwork on file for this link.")
    content, mime_type, filename = art
    safe_name = (filename or "artwork").replace("\r", "").replace("\n", "").replace('"', "'")
    return Response(content=content, media_type=mime_type or "application/octet-stream",
                    headers={"Content-Disposition": f'inline; filename="{safe_name}"'})
