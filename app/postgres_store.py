"""Real storage backend. The only module in this app that imports psycopg2."""
import uuid
from contextlib import contextmanager
from datetime import timedelta
from typing import Optional

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

from app.security import new_approval_token
from app.store import ApprovalRequest, Shop, Store, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS shops (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    api_key_hash        TEXT NOT NULL UNIQUE,
    license_serial      TEXT NOT NULL UNIQUE,
    license_status      TEXT NOT NULL DEFAULT 'trial',
    license_expires_at  TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS approval_requests (
    id                    TEXT PRIMARY KEY,
    token                 TEXT NOT NULL UNIQUE,
    shop_id               TEXT NOT NULL REFERENCES shops(id),
    shop_name             TEXT NOT NULL DEFAULT '',
    shop_job_ref          TEXT NOT NULL,
    customer_name         TEXT NOT NULL,
    order_number          TEXT NOT NULL,
    summary               TEXT NOT NULL DEFAULT '',
    status                TEXT NOT NULL DEFAULT 'pending',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at            TIMESTAMPTZ NOT NULL,
    responded_at          TIMESTAMPTZ,
    response              TEXT,
    response_comment      TEXT NOT NULL DEFAULT '',
    delivered_to_shop_at  TIMESTAMPTZ,
    acked_by_shop_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_approval_shop_undelivered
    ON approval_requests(shop_id) WHERE status = 'responded' AND acked_by_shop_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_approval_token ON approval_requests(token);
-- Additive (Postgres ADD COLUMN IF NOT EXISTS is idempotent, unlike SQLite -- no
-- PRAGMA-check dance needed, matching the "no migration framework for v1" convention).
-- artwork_bytes is deliberately excluded from every SELECT below except the one that
-- actually serves the image, so a plain get/list of a request stays cheap.
ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS artwork_bytes BYTEA;
ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS artwork_mime_type TEXT;
ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS artwork_filename TEXT;
"""

# Every column except artwork_bytes -- used everywhere an ApprovalRequest is read back,
# so the (potentially large) blob is never loaded except by get_artwork_by_token.
_APPROVAL_COLUMNS = """id, token, shop_id, shop_name, shop_job_ref, customer_name, order_number, summary,
    status, created_at, expires_at, responded_at, response, response_comment,
    delivered_to_shop_at, acked_by_shop_at, artwork_filename, artwork_mime_type"""


def _row_to_shop(row) -> Shop:
    return Shop(id=row["id"], name=row["name"], api_key_hash=row["api_key_hash"],
               license_serial=row["license_serial"], license_status=row["license_status"],
               license_expires_at=row["license_expires_at"], created_at=row["created_at"],
               last_seen_at=row["last_seen_at"])


def _row_to_approval(row) -> ApprovalRequest:
    return ApprovalRequest(id=row["id"], token=row["token"], shop_id=row["shop_id"],
                           shop_name=row.get("shop_name", ""),
                           shop_job_ref=row["shop_job_ref"], customer_name=row["customer_name"],
                           order_number=row["order_number"], summary=row["summary"],
                           status=row["status"], created_at=row["created_at"],
                           expires_at=row["expires_at"], responded_at=row["responded_at"],
                           response=row["response"], response_comment=row["response_comment"] or "",
                           delivered_to_shop_at=row["delivered_to_shop_at"],
                           acked_by_shop_at=row["acked_by_shop_at"],
                           artwork_filename=row.get("artwork_filename"),
                           artwork_mime_type=row.get("artwork_mime_type"))


class PostgresStore(Store):
    def __init__(self, dsn: str, minconn: int = 1, maxconn: int = 5):
        self._pool = psycopg2.pool.SimpleConnectionPool(minconn, maxconn, dsn)

    @contextmanager
    def _cursor(self, commit: bool = False):
        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    def init_schema(self) -> None:
        with self._cursor(commit=True) as cur:
            cur.execute(SCHEMA)

    def create_shop(self, name, api_key_hash, license_serial, license_status="trial", license_expires_at=None) -> Shop:
        with self._cursor(commit=True) as cur:
            cur.execute(
                """INSERT INTO shops (id, name, api_key_hash, license_serial, license_status, license_expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING *""",
                (str(uuid.uuid4()), name, api_key_hash, license_serial, license_status, license_expires_at))
            return _row_to_shop(cur.fetchone())

    def get_shop_by_key_hash(self, api_key_hash: str) -> Optional[Shop]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM shops WHERE api_key_hash = %s", (api_key_hash,))
            row = cur.fetchone()
            return _row_to_shop(row) if row else None

    def touch_last_seen(self, shop_id: str) -> None:
        with self._cursor(commit=True) as cur:
            cur.execute("UPDATE shops SET last_seen_at = now() WHERE id = %s", (shop_id,))

    def create_approval_request(self, shop_id, shop_name, shop_job_ref, customer_name, order_number, summary, expires_in_days) -> ApprovalRequest:
        token = new_approval_token()
        expires_at = utcnow() + timedelta(days=expires_in_days)
        with self._cursor(commit=True) as cur:
            cur.execute(
                f"""INSERT INTO approval_requests
                   (id, token, shop_id, shop_name, shop_job_ref, customer_name, order_number, summary, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING {_APPROVAL_COLUMNS}""",
                (str(uuid.uuid4()), token, shop_id, shop_name, shop_job_ref, customer_name, order_number, summary, expires_at))
            return _row_to_approval(cur.fetchone())

    def get_approval_by_token(self, token: str) -> Optional[ApprovalRequest]:
        with self._cursor() as cur:
            cur.execute(f"SELECT {_APPROVAL_COLUMNS} FROM approval_requests WHERE token = %s", (token,))
            row = cur.fetchone()
            return _row_to_approval(row) if row else None

    def record_response(self, token: str, response: str, comment: str) -> Optional[ApprovalRequest]:
        with self._cursor(commit=True) as cur:
            cur.execute(
                f"""UPDATE approval_requests SET status = 'responded', response = %s,
                       response_comment = %s, responded_at = now()
                   WHERE token = %s AND status = 'pending' AND expires_at > now()
                   RETURNING {_APPROVAL_COLUMNS}""",
                (response, comment, token))
            row = cur.fetchone()
            if row:
                return _row_to_approval(row)
            # Already responded (or expired/unknown) -- return current state so the
            # caller can render the right read-only page instead of erroring.
            cur.execute(f"SELECT {_APPROVAL_COLUMNS} FROM approval_requests WHERE token = %s", (token,))
            row = cur.fetchone()
            return _row_to_approval(row) if row else None

    def get_undelivered_for_shop(self, shop_id: str) -> list[ApprovalRequest]:
        with self._cursor() as cur:
            cur.execute(
                f"""SELECT {_APPROVAL_COLUMNS} FROM approval_requests
                   WHERE shop_id = %s AND status = 'responded' AND acked_by_shop_at IS NULL
                   ORDER BY responded_at""", (shop_id,))
            return [_row_to_approval(r) for r in cur.fetchall()]

    def mark_delivered(self, ids: list[str]) -> None:
        if not ids:
            return
        with self._cursor(commit=True) as cur:
            cur.execute("UPDATE approval_requests SET delivered_to_shop_at = now() WHERE id = ANY(%s)", (ids,))

    def set_artwork(self, shop_id: str, request_id: str, filename: str, mime_type: str, content: bytes) -> bool:
        with self._cursor(commit=True) as cur:
            cur.execute(
                """UPDATE approval_requests SET artwork_bytes = %s, artwork_mime_type = %s, artwork_filename = %s
                   WHERE id = %s AND shop_id = %s RETURNING id""",
                (psycopg2.Binary(content), mime_type, filename, request_id, shop_id))
            return cur.fetchone() is not None

    def get_artwork_by_token(self, token: str) -> Optional[tuple[bytes, str, str]]:
        with self._cursor() as cur:
            cur.execute(
                """SELECT artwork_bytes, artwork_mime_type, artwork_filename FROM approval_requests
                   WHERE token = %s AND artwork_bytes IS NOT NULL""", (token,))
            row = cur.fetchone()
            if not row:
                return None
            return bytes(row["artwork_bytes"]), row["artwork_mime_type"], row["artwork_filename"]

    def ack_approvals(self, shop_id: str, ids: list[str]) -> None:
        if not ids:
            return
        with self._cursor(commit=True) as cur:
            cur.execute(
                "UPDATE approval_requests SET acked_by_shop_at = now() WHERE shop_id = %s AND id = ANY(%s)",
                (shop_id, ids))
