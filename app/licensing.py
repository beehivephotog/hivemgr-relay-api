"""Effective license status: expiry is computed on read, not enforced by a cron job."""
from app.schemas import LicenseStatus
from app.store import Shop, utcnow


def effective_license(shop: Shop) -> LicenseStatus:
    status = shop.license_status
    if status in ("active", "trial") and shop.license_expires_at and utcnow() > shop.license_expires_at:
        status = "expired"
    return LicenseStatus(status=status, expires_at=shop.license_expires_at)
