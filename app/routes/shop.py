"""Shop-authenticated routes: the one combined sync call, and creating an approval request."""
import os

from fastapi import APIRouter, Depends

from app.auth import get_current_shop
from app.deps import get_store
from app.licensing import effective_license
from app.schemas import (ApprovalEvent, CreateApprovalRequest, CreateApprovalResponse,
                         SyncRequest, SyncResponse)
from app.store import Shop, Store, utcnow

router = APIRouter(prefix="/api/v1", tags=["shop"])


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
