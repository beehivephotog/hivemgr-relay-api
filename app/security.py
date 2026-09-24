"""Token/key generation and hashing. No secrets are ever stored in plaintext."""
import hashlib
import hmac
import secrets

API_KEY_PREFIX = "hmgr_"


def new_api_key() -> str:
    """A raw API key handed to a shop exactly once, at issuance time."""
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(raw_key: str) -> str:
    """One-way hash stored in the database. Never reversible, never logged."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_api_key(raw_key), stored_hash)


def new_approval_token() -> str:
    """High-entropy, unguessable token embedded in the customer-facing link."""
    return secrets.token_urlsafe(32)
