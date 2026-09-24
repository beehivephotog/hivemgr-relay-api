"""Request/response shapes for the shop-facing API. Kept deliberately small for v1."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class LicenseStatus(BaseModel):
    status: Literal["trial", "active", "suspended", "expired"]
    expires_at: Optional[datetime] = None


class ApprovalEvent(BaseModel):
    """One approval response, delivered to the shop's poller."""
    id: str
    shop_job_ref: str
    response: Literal["approved", "changes_requested"]
    response_comment: str = ""
    responded_at: datetime


class SyncRequest(BaseModel):
    acks: list[str] = Field(default_factory=list, description="approval_request ids the shop fully applied last cycle")


class SyncResponse(BaseModel):
    license: LicenseStatus
    approvals: list[ApprovalEvent]
    server_time: datetime


class CreateApprovalRequest(BaseModel):
    shop_job_ref: str = Field(..., max_length=200)
    customer_name: str = Field(..., max_length=200)
    order_number: str = Field(..., max_length=100)
    summary: str = Field(..., max_length=4000, description="Customer-safe line-item text; no pricing, no artwork.")
    expires_in_days: int = Field(default=30, ge=1, le=180)


class CreateApprovalResponse(BaseModel):
    id: str
    token: str
    approve_url: str


class ApprovalSubmission(BaseModel):
    response: Literal["approved", "changes_requested"]
    comment: str = Field(default="", max_length=4000)
