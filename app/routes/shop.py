"""Shop-authenticated routes: the one combined sync call, creating an approval request,
and (optionally, best-effort from the shop's side) attaching its artwork file."""
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.auth import get_current_shop
from app.deps import get_store
from app.licensing import effective_license
from app.schemas import (ApprovalEvent, CreateApprovalRequest, CreateApprovalResponse,
                         SyncRequest, SyncResponse)
from app.store import Shop, Store, utcnow

router = APIRouter(prefix="/api/v1", tags=["shop"])

# Matches the main HiveMGR app's own upload cap (shop_artwork.py) -- the file already
# passed that check once on the shop's PC before ever reaching here.
MAX_ARTWORK_BYTES = 20 * 1024 * 1024


@router.post("/sync", response_model=SyncResponse)
def sync(body: SyncRequest, shop: Shop = Depends(get_current_shop), store: Store = Depends(get_store)) -> SyncResponse:
    store.touch_last_seen(shop.id)
    if body.acks:
        store.ack_approvals(shop.id, body.acks)
    pending = store.get_undelivered_for_shop(shop.id)
    if pending:
        store.mark_delivered([r.id for r in pending])
    events = [ApprovalEvent(id=r.id, shop_job_ref=r.shop_job_ref, response=r.response,
                            response_comment=r.response_comment, responded_at=r.responded_at)
             for r in pending]
    return SyncResponse(license=effective_license(shop), approvals=events, server_time=utcnow())


@router.post("/approval-requests", response_model=CreateApprovalResponse)
def create_approval_request(body: CreateApprovalRequest, shop: Shop = Depends(get_current_shop),
                            store: Store = Depends(get_store)) -> CreateApprovalResponse:
    req = store.create_approval_request(shop.id, shop.name, body.shop_job_ref, body.customer_name,
                                        body.order_number, body.summary, body.expires_in_days)
    base_url = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    approve_url = f"{base_url}/approve/{req.token}" if base_url else f"/approve/{req.token}"
    return CreateApprovalResponse(id=req.id, token=req.token, approve_url=approve_url)


@router.post("/approval-requests/{request_id}/artwork")
async def upload_artwork(request_id: str, file: UploadFile = File(...),
                         shop: Shop = Depends(get_current_shop), store: Store = Depends(get_store)):
    """Best-effort from the shop's side (see cloud_sync.py in the main app): if this fails
    or is never called, the approval request and its email still work fine -- this only
    adds an inline preview to the public approval page."""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file.")
    if len(content) > MAX_ARTWORK_BYTES:
        raise HTTPException(status_code=413, detail="Artwork file is too large.")
    ok = store.set_artwork(shop.id, request_id, file.filename or "artwork",
                           file.content_type or "application/octet-stream", content)
    if not ok:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    return {"ok": True}
