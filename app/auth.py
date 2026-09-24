"""Shop authentication for the /api/v1/* routes: a per-shop API key in a header."""
from fastapi import Depends, Header, HTTPException

from app.deps import get_store
from app.security import hash_api_key
from app.store import Shop, Store


def get_current_shop(x_hivemgr_key: str = Header(..., alias="X-HiveMGR-Key"),
                     store: Store = Depends(get_store)) -> Shop:
    shop = store.get_shop_by_key_hash(hash_api_key(x_hivemgr_key))
    if not shop:
        raise HTTPException(status_code=401, detail="Invalid or unrecognized API key.")
    return shop
