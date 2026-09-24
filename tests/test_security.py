from app.security import hash_api_key, new_api_key, new_approval_token, verify_api_key


def test_api_key_is_high_entropy_and_prefixed():
    key = new_api_key()
    assert key.startswith("hmgr_")
    assert len(key) > 40


def test_api_keys_are_unique():
    assert new_api_key() != new_api_key()


def test_hash_is_deterministic_and_one_way():
    key = new_api_key()
    h1, h2 = hash_api_key(key), hash_api_key(key)
    assert h1 == h2
    assert key not in h1


def test_verify_api_key():
    key = new_api_key()
    stored = hash_api_key(key)
    assert verify_api_key(key, stored)
    assert not verify_api_key("hmgr_wrong", stored)
    assert not verify_api_key(new_api_key(), stored)


def test_approval_token_is_url_safe_and_unique():
    t1, t2 = new_approval_token(), new_approval_token()
    assert t1 != t2
    assert len(t1) > 30
    assert all(c.isalnum() or c in "-_" for c in t1)
