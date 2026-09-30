"""Storage interface. Route code depends only on this ABC, never on psycopg2 directly,
so tests can run against InMemoryStore with no database at all. PostgresStore (the real
implementation) lives in postgres_store.py and is the only module that imports psycopg2.
"""
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Shop:
    id: str
    name: str
    api_key_hash: str
    license_serial: str
    license_status: str  # 'trial' | 'active' | 'suspended' | 'expired'
    license_expires_at: Optional[datetime]
    created_at: datetime
    last_seen_at: Optional[datetime]


@dataclass
class ApprovalRequest:
    id: str
    token: str
    shop_id: str
    shop_name: str
    shop_job_ref: str
    customer_name: str
    order_number: str
    summary: str
    status: str  # 'pending' | 'responded' | 'expired'
    created_at: datetime
    expires_at: datetime
    responded_at: Optional[datetime] = None
    response: Optional[str] = None  # 'approved' | 'changes_requested'
    response_comment: str = ""
    delivered_to_shop_at: Optional[datetime] = None
    acked_by_shop_at: Optional[datetime] = None
    # Metadata only -- never the bytes themselves, so a plain get/list stays cheap.
    # The bytes are fetched separately, only when the artwork is actually served.
    artwork_filename: Optional[str] = None
    artwork_mime_type: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        return self.status == "pending" and utcnow() > self.expires_at

    @property
    def has_artwork(self) -> bool:
        return bool(self.artwork_filename)

    @property
    def artwork_is_image(self) -> bool:
        return bool(self.artwork_mime_type) and self.artwork_mime_type.startswith("image/")


class Store(ABC):
    @abstractmethod
    def init_schema(self) -> None: ...

    @abstractmethod
    def create_shop(self, name: str, api_key_hash: str, license_serial: str,
                    license_status: str = "trial",
                    license_expires_at: Optional[datetime] = None) -> Shop: ...

    @abstractmethod
    def get_shop_by_key_hash(self, api_key_hash: str) -> Optional[Shop]: ...

    @abstractmethod
    def touch_last_seen(self, shop_id: str) -> None: ...

    @abstractmethod
    def create_approval_request(self, shop_id: str, shop_name: str, shop_job_ref: str, customer_name: str,
                                order_number: str, summary: str, expires_in_days: int) -> ApprovalRequest: ...

    @abstractmethod
    def get_approval_by_token(self, token: str) -> Optional[ApprovalRequest]: ...

    @abstractmethod
    def record_response(self, token: str, response: str, comment: str) -> Optional[ApprovalRequest]: ...

    @abstractmethod
    def get_undelivered_for_shop(self, shop_id: str) -> list[ApprovalRequest]:
        """Responded approvals the shop hasn't acked yet -- redelivered every sync until acked."""
        ...

    @abstractmethod
    def mark_delivered(self, ids: list[str]) -> None: ...

    @abstractmethod
    def ack_approvals(self, shop_id: str, ids: list[str]) -> None: ...

    @abstractmethod
    def set_artwork(self, shop_id: str, request_id: str, filename: str, mime_type: str, content: bytes) -> bool:
        """Attaches the proof file to an existing request, so the public approval page can
        show it inline. Shop-scoped (only the owning shop may attach to its own request).
        Returns False if the request doesn't exist or belongs to a different shop."""
        ...

    @abstractmethod
    def get_artwork_by_token(self, token: str) -> Optional[tuple[bytes, str, str]]:
        """Returns (content, mime_type, filename) for the public page to serve, or None if
        no artwork was ever attached (or the token is unknown)."""
        ...


class InMemoryStore(Store):
    """Thread-safe in-process store used by the test suite. Same semantics as PostgresStore,
    no persistence, no external dependency."""

    def __init__(self):
        self._lock = threading.Lock()
        self._shops: dict[str, Shop] = {}
        self._approvals: dict[str, ApprovalRequest] = {}
        self._by_token: dict[str, str] = {}
        self._artwork: dict[str, tuple[bytes, str, str]] = {}  # request_id -> (content, mime_type, filename)
        self._seq = 0

    def init_schema(self) -> None:
        pass

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{self._seq:08d}"

    def create_shop(self, name, api_key_hash, license_serial, license_status="trial", license_expires_at=None) -> Shop:
        with self._lock:
            shop = Shop(id=self._next_id("shop"), name=name, api_key_hash=api_key_hash,
                       license_serial=license_serial, license_status=license_status,
                       license_expires_at=license_expires_at, created_at=utcnow(), last_seen_at=None)
            self._shops[shop.id] = shop
            return shop

    def get_shop_by_key_hash(self, api_key_hash: str) -> Optional[Shop]:
        with self._lock:
            for shop in self._shops.values():
                if shop.api_key_hash == api_key_hash:
                    return shop
            return None

    def touch_last_seen(self, shop_id: str) -> None:
        with self._lock:
            if shop_id in self._shops:
                self._shops[shop_id].last_seen_at = utcnow()

    def create_approval_request(self, shop_id, shop_name, shop_job_ref, customer_name, order_number, summary, expires_in_days) -> ApprovalRequest:
        with self._lock:
            now = utcnow()
            req = ApprovalRequest(id=self._next_id("appr"), token=None, shop_id=shop_id, shop_name=shop_name,
                                  shop_job_ref=shop_job_ref, customer_name=customer_name,
                                  order_number=order_number, summary=summary, status="pending",
                                  created_at=now, expires_at=now + timedelta(days=expires_in_days))
            from app.security import new_approval_token
            req.token = new_approval_token()
            self._approvals[req.id] = req
            self._by_token[req.token] = req.id
            return req

    def get_approval_by_token(self, token: str) -> Optional[ApprovalRequest]:
        with self._lock:
            rid = self._by_token.get(token)
            return self._approvals.get(rid) if rid else None

    def record_response(self, token: str, response: str, comment: str) -> Optional[ApprovalRequest]:
        with self._lock:
            rid = self._by_token.get(token)
            if not rid:
                return None
            req = self._approvals[rid]
            if req.status == "pending" and not req.is_expired:
                req.status = "responded"
                req.response = response
                req.response_comment = comment
                req.responded_at = utcnow()
            return req

    def get_undelivered_for_shop(self, shop_id: str) -> list[ApprovalRequest]:
        with self._lock:
            return [r for r in self._approvals.values()
                   if r.shop_id == shop_id and r.status == "responded" and r.acked_by_shop_at is None]

    def mark_delivered(self, ids: list[str]) -> None:
        with self._lock:
            now = utcnow()
            for rid in ids:
                if rid in self._approvals:
                    self._approvals[rid].delivered_to_shop_at = now

    def ack_approvals(self, shop_id: str, ids: list[str]) -> None:
        with self._lock:
            now = utcnow()
            for rid in ids:
                req = self._approvals.get(rid)
                if req and req.shop_id == shop_id:
                    req.acked_by_shop_at = now

    def set_artwork(self, shop_id: str, request_id: str, filename: str, mime_type: str, content: bytes) -> bool:
        with self._lock:
            req = self._approvals.get(request_id)
            if not req or req.shop_id != shop_id:
                return False
            req.artwork_filename = filename
            req.artwork_mime_type = mime_type
            self._artwork[request_id] = (content, mime_type, filename)
            return True

    def get_artwork_by_token(self, token: str) -> Optional[tuple[bytes, str, str]]:
        with self._lock:
            rid = self._by_token.get(token)
            return self._artwork.get(rid) if rid else None
