from datetime import timedelta

from app.rate_limit import _hits


def test_unknown_token_shows_not_found(client):
    r = client.get("/approve/does-not-exist")
    assert r.status_code == 200
    assert "not recognized" in r.text.lower()


def test_pending_approval_shows_form(client, store, shop_and_key):
    shop, _ = shop_and_key
    req = store.create_approval_request(shop.id, shop.name, "job-1", "Jane", "JG-1", "10 signs", 30)
    r = client.get(f"/approve/{req.token}")
    assert r.status_code == 200
    assert "<form" in r.text
    assert "Approve" in r.text
    assert "Request Changes" in r.text


def test_submit_approved(client, store, shop_and_key):
    shop, _ = shop_and_key
    req = store.create_approval_request(shop.id, shop.name, "job-1", "Jane", "JG-1", "10 signs", 30)
    r = client.post(f"/approve/{req.token}", data={"response": "approved", "comment": "Looks perfect"})
    assert r.status_code == 200
    assert "you approved this order" in r.text.lower()
    assert "Looks perfect" in r.text
    updated = store.get_approval_by_token(req.token)
    assert updated.status == "responded"
    assert updated.response == "approved"


def test_submit_changes_requested(client, store, shop_and_key):
    shop, _ = shop_and_key
    req = store.create_approval_request(shop.id, shop.name, "job-1", "Jane", "JG-1", "10 signs", 30)
    r = client.post(f"/approve/{req.token}", data={"response": "changes_requested", "comment": "Wrong color"})
    assert "requested changes" in r.text.lower()
    assert "Wrong color" in r.text


def test_second_submission_does_not_overwrite_first(client, store, shop_and_key):
    shop, _ = shop_and_key
    req = store.create_approval_request(shop.id, shop.name, "job-1", "Jane", "JG-1", "10 signs", 30)
    client.post(f"/approve/{req.token}", data={"response": "approved", "comment": "first"})
    r2 = client.post(f"/approve/{req.token}", data={"response": "changes_requested", "comment": "second"})
    assert "you approved this order" in r2.text.lower()  # still shows the original decision
    assert "first" in r2.text
    assert "second" not in r2.text


def test_viewing_after_response_is_read_only_not_an_error(client, store, shop_and_key):
    shop, _ = shop_and_key
    req = store.create_approval_request(shop.id, shop.name, "job-1", "Jane", "JG-1", "10 signs", 30)
    client.post(f"/approve/{req.token}", data={"response": "approved", "comment": ""})
    r = client.get(f"/approve/{req.token}")
    assert r.status_code == 200
    assert "you approved this order" in r.text.lower()


def test_expired_request_shows_expired_page_not_form(client, store, shop_and_key):
    shop, _ = shop_and_key
    req = store.create_approval_request(shop.id, shop.name, "job-1", "Jane", "JG-1", "10 signs", expires_in_days=1)
    req.expires_at = req.expires_at - timedelta(days=2)  # force it into the past for the test
    r = client.get(f"/approve/{req.token}")
    assert r.status_code == 200
    assert "expired" in r.text.lower()
    assert "<form" not in r.text


def test_rate_limit_blocks_after_threshold(client, store, shop_and_key):
    _hits.clear()
    shop, _ = shop_and_key
    req = store.create_approval_request(shop.id, shop.name, "job-1", "Jane", "JG-1", "10 signs", 30)
    last = None
    for _ in range(11):
        last = client.post(f"/approve/{req.token}", data={"response": "approved", "comment": ""})
    assert last.status_code == 429
