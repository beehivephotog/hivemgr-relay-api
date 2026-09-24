from datetime import timedelta

from app.security import hash_api_key, new_api_key
from app.store import utcnow


def test_sync_requires_api_key(client):
    r = client.post("/api/v1/sync", json={"acks": []})
    assert r.status_code == 422  # missing required header


def test_sync_rejects_unknown_key(client):
    r = client.post("/api/v1/sync", json={"acks": []}, headers={"X-HiveMGR-Key": "hmgr_nope"})
    assert r.status_code == 401


def test_empty_sync_returns_license_and_no_approvals(client, auth_headers):
    r = client.post("/api/v1/sync", json={"acks": []}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["license"]["status"] == "active"
    assert body["approvals"] == []


def test_responded_approval_is_delivered_once_and_acked(client, auth_headers, store, shop_and_key):
    shop, _ = shop_and_key
    req = store.create_approval_request(shop.id, shop.name, "job-42", "Jane Doe", "JG-1050", "100 stickers", 30)
    store.record_response(req.token, "approved", "Looks great")

    r1 = client.post("/api/v1/sync", json={"acks": []}, headers=auth_headers)
    approvals = r1.json()["approvals"]
    assert len(approvals) == 1
    assert approvals[0]["shop_job_ref"] == "job-42"
    assert approvals[0]["response"] == "approved"
    assert approvals[0]["response_comment"] == "Looks great"

    # Redelivered until acked (at-least-once delivery).
    r2 = client.post("/api/v1/sync", json={"acks": []}, headers=auth_headers)
    assert len(r2.json()["approvals"]) == 1

    # Ack it -> stops appearing.
    r3 = client.post("/api/v1/sync", json={"acks": [approvals[0]["id"]]}, headers=auth_headers)
    assert r3.json()["approvals"] == []
    r4 = client.post("/api/v1/sync", json={"acks": []}, headers=auth_headers)
    assert r4.json()["approvals"] == []


def test_pending_unresponded_approval_is_not_delivered(client, auth_headers, store, shop_and_key):
    shop, _ = shop_and_key
    store.create_approval_request(shop.id, shop.name, "job-1", "Jane", "JG-1", "stuff", 30)
    r = client.post("/api/v1/sync", json={"acks": []}, headers=auth_headers)
    assert r.json()["approvals"] == []


def test_sync_only_returns_the_authenticated_shops_approvals(client, store):
    key_a, key_b = new_api_key(), new_api_key()
    shop_a = store.create_shop("Shop A", hash_api_key(key_a), "A-1", "active")
    shop_b = store.create_shop("Shop B", hash_api_key(key_b), "B-1", "active")
    req_a = store.create_approval_request(shop_a.id, shop_a.name, "a-job", "Cust A", "A-1", "x", 30)
    store.record_response(req_a.token, "approved", "")
    req_b = store.create_approval_request(shop_b.id, shop_b.name, "b-job", "Cust B", "B-1", "x", 30)
    store.record_response(req_b.token, "approved", "")

    r = client.post("/api/v1/sync", json={"acks": []}, headers={"X-HiveMGR-Key": key_a})
    refs = [a["shop_job_ref"] for a in r.json()["approvals"]]
    assert refs == ["a-job"]


def test_shop_cannot_ack_another_shops_approval(client, store):
    key_a, key_b = new_api_key(), new_api_key()
    shop_a = store.create_shop("Shop A", hash_api_key(key_a), "A-1", "active")
    shop_b = store.create_shop("Shop B", hash_api_key(key_b), "B-1", "active")
    req_b = store.create_approval_request(shop_b.id, shop_b.name, "b-job", "Cust B", "B-1", "x", 30)
    store.record_response(req_b.token, "approved", "")

    client.post("/api/v1/sync", json={"acks": [req_b.id]}, headers={"X-HiveMGR-Key": key_a})
    r = client.post("/api/v1/sync", json={"acks": []}, headers={"X-HiveMGR-Key": key_b})
    assert len(r.json()["approvals"]) == 1  # shop A's ack attempt on shop B's row was a no-op


def test_expired_license_reported_even_without_status_flip(client, store):
    key = new_api_key()
    shop = store.create_shop("Expiring Co", hash_api_key(key), "EXP-1", "active",
                             license_expires_at=utcnow() - timedelta(days=1))
    r = client.post("/api/v1/sync", json={"acks": []}, headers={"X-HiveMGR-Key": key})
    assert r.json()["license"]["status"] == "expired"


def test_suspended_shop_can_still_sync(client, store):
    key = new_api_key()
    store.create_shop("Suspended Co", hash_api_key(key), "SUS-1", "suspended")
    r = client.post("/api/v1/sync", json={"acks": []}, headers={"X-HiveMGR-Key": key})
    assert r.status_code == 200
    assert r.json()["license"]["status"] == "suspended"
