from datetime import timedelta

from app.licensing import effective_license
from app.store import utcnow


def make_shop(store, status, expires_at=None):
    from app.security import hash_api_key, new_api_key
    return store.create_shop("Co", hash_api_key(new_api_key()), f"SER-{status}-{id(expires_at)}",
                             status, expires_at)


def test_active_without_expiry_stays_active(store):
    shop = make_shop(store, "active", None)
    assert effective_license(shop).status == "active"


def test_active_with_future_expiry_stays_active(store):
    shop = make_shop(store, "active", utcnow() + timedelta(days=30))
    assert effective_license(shop).status == "active"


def test_active_with_past_expiry_reports_expired(store):
    shop = make_shop(store, "active", utcnow() - timedelta(seconds=1))
    assert effective_license(shop).status == "expired"


def test_trial_with_past_expiry_reports_expired(store):
    shop = make_shop(store, "trial", utcnow() - timedelta(days=1))
    assert effective_license(shop).status == "expired"


def test_suspended_stays_suspended_regardless_of_expiry(store):
    shop = make_shop(store, "suspended", utcnow() + timedelta(days=30))
    assert effective_license(shop).status == "suspended"


def test_explicitly_expired_stays_expired(store):
    shop = make_shop(store, "expired", None)
    assert effective_license(shop).status == "expired"
