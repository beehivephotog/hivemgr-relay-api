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
