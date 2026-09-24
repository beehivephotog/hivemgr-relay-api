"""FastAPI dependency wiring. Tests override get_store with an InMemoryStore via
app.dependency_overrides -- nothing in routes/ ever imports psycopg2 or PostgresStore."""
import os

from app.store import Store

_store: Store | None = None


def get_store() -> Store:
    global _store
    if _store is None:
        from app.postgres_store import PostgresStore
        dsn = os.environ["DATABASE_URL"]
        _store = PostgresStore(dsn)
        _store.init_schema()
    return _store
