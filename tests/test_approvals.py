def test_create_approval_request_returns_token_and_url(client, auth_headers):
    r = client.post("/api/v1/approval-requests", headers=auth_headers, json={
        "shop_job_ref": "job-99", "customer_name": "Jane Doe", "order_number": "JG-1099",
        "summary": "100 x Premium Stickers (3x3 in)",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["id"]
    assert len(body["token"]) > 30
    assert body["token"] in body["approve_url"]


def test_create_approval_request_requires_auth(client):
    r = client.post("/api/v1/approval-requests", json={
        "shop_job_ref": "job-1", "customer_name": "Jane", "order_number": "J-1", "summary": "x",
    })
    assert r.status_code == 422


def test_created_request_is_immediately_visible_at_its_public_page(client, auth_headers):
    created = client.post("/api/v1/approval-requests", headers=auth_headers, json={
        "shop_job_ref": "job-1", "customer_name": "Jane Doe", "order_number": "JG-1",
        "summary": "10 x Yard Signs",
    }).json()
    r = client.get(f"/approve/{created['token']}")
    assert r.status_code == 200
    assert "JG-1" in r.text
    assert "Jane Doe" in r.text
    assert "10 x Yard Signs" in r.text
    assert "Test Sign Co" in r.text  # shop name, so the customer knows who's asking


def test_upload_artwork_attaches_to_the_request(client, auth_headers):
    created = client.post("/api/v1/approval-requests", headers=auth_headers, json={
        "shop_job_ref": "job-1", "customer_name": "Jane Doe", "order_number": "JG-1",
        "summary": "10 x Yard Signs",
    }).json()
    r = client.post(f"/api/v1/approval-requests/{created['id']}/artwork", headers=auth_headers,
                    files={"file": ("proof.png", b"\x89PNG\r\n\x1a\nfake png bytes", "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_upload_artwork_requires_auth(client):
    r = client.post("/api/v1/approval-requests/appr_1/artwork",
                    files={"file": ("proof.png", b"x", "image/png")})
    assert r.status_code == 422  # missing required header, same as every other shop route


def test_upload_artwork_rejects_unknown_request_id(client, auth_headers):
    r = client.post("/api/v1/approval-requests/does-not-exist/artwork", headers=auth_headers,
                    files={"file": ("proof.png", b"x", "image/png")})
    assert r.status_code == 404


def test_upload_artwork_rejects_another_shops_request(client, store):
    from app.security import hash_api_key, new_api_key
    key_a, key_b = new_api_key(), new_api_key()
    shop_a = store.create_shop("Shop A", hash_api_key(key_a), "A-1", "active")
    store.create_shop("Shop B", hash_api_key(key_b), "B-1", "active")
    req_a = store.create_approval_request(shop_a.id, shop_a.name, "a-job", "Cust A", "A-1", "x", 30)
    r = client.post(f"/api/v1/approval-requests/{req_a.id}/artwork", headers={"X-HiveMGR-Key": key_b},
                    files={"file": ("proof.png", b"x", "image/png")})
    assert r.status_code == 404  # shop B has no visibility into shop A's request


def test_upload_artwork_rejects_oversized_file(client, auth_headers):
    created = client.post("/api/v1/approval-requests", headers=auth_headers, json={
        "shop_job_ref": "job-1", "customer_name": "Jane Doe", "order_number": "JG-1",
        "summary": "10 x Yard Signs",
    }).json()
    oversized = b"x" * (20 * 1024 * 1024 + 1)
    r = client.post(f"/api/v1/approval-requests/{created['id']}/artwork", headers=auth_headers,
                    files={"file": ("proof.png", oversized, "image/png")})
    assert r.status_code == 413
