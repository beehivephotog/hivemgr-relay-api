# HiveMGR Relay

Standalone cloud backend for HiveMGR (the local shop-management app). Two jobs:

1. **Artwork-approval relay** — a customer clicks a link in an email, approves or
   requests changes on a simple public page here, and the shop's local install picks
   up the response by polling out to this service. This service never reaches into a
   shop's network — there is no inbound call in either direction except the customer's
   own browser hitting the public `/approve/<token>` page.
2. **License check** — validates a per-shop serial/license on the same poll.

Deliberately small for v1: 4 endpoints, 2 tables, no admin UI (see `scripts/create_shop.py`
for onboarding), no self-serve signup.

## Why polling, not a webhook

A shop's local install has no public IP and no port forwarding — matching HiveMGR's
LAN-only design. So every shop-facing call is initiated by the shop (`POST /api/v1/sync`,
roughly every 5 minutes while it's running); this service only ever *responds*, it never
calls out to a shop. Only the customer-facing `/approve/<token>` page is genuinely public.

## What never leaves the shop

The approval page shows an order number, the shop's name, and a customer-safe
line-item summary — no artwork file, no pricing, no internal notes. The artwork preview
the customer needs to judge is in the *email* they already received (HiveMGR embeds it
there); this service only needs to carry the decision, not the file.

## Sync protocol

`POST /api/v1/sync` (header `X-HiveMGR-Key: <shop's API key>`)

```json
// request
{"acks": ["appr_00000001"]}   // ids the shop fully applied from the *previous* sync

// response
{
  "license": {"status": "active", "expires_at": null},
  "approvals": [
    {"id": "appr_00000002", "shop_job_ref": "job-42", "response": "approved",
     "response_comment": "Looks great", "responded_at": "2026-09-24T18:00:00Z"}
  ],
  "server_time": "2026-09-24T18:05:00Z"
}
```

Delivery is at-least-once: an approval keeps being returned every sync until the shop
acks its id in a *later* request. This means shop-side apply logic must be idempotent
(dedupe by `id`) — the same principle already used for `email_log` in the main app.
A shop offline for weeks loses nothing; it just gets a bigger batch on its next sync.

`POST /api/v1/approval-requests` — the shop calls this right before emailing the
approval link to a customer. Returns `{id, token, approve_url}`.

## Schema

See `app/postgres_store.py::SCHEMA` for the authoritative DDL (`shops`,
`approval_requests`). Runs automatically as `CREATE TABLE IF NOT EXISTS` on startup —
no migration framework for v1, matching the main app's `shop_db.py` convention.

## Local development

```
py -3 -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\pytest tests -v
```

Tests never touch a real database — `app/store.py` defines the storage interface,
`app/postgres_store.py` is the only module that imports psycopg2, and tests inject
`InMemoryStore` via FastAPI's `dependency_overrides`. Running the app for real
(`uvicorn app.main:app`) does need `DATABASE_URL` set (see `.env.example`).

## Onboarding a shop

```
DATABASE_URL=postgresql://... python scripts/create_shop.py "JG Sign Company" HMGR-0001
```

Prints a raw API key once — paste it into HiveMGR's Settings → Cloud sync. It is
hashed before storage and cannot be recovered; re-run to issue a new key if it's lost
(this creates a *new* shop row for now — v1 has no key-rotation-in-place command yet).

## Deploying

Render web service, Python runtime:
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`
- Env vars: `DATABASE_URL` (from the Render Postgres instance), `PUBLIC_BASE_URL`
  (this service's own public URL, used to build `approve_url` in the create-request
  response — e.g. `https://hivemgr-relay-api.onrender.com`)

Free tier to start. The shop-side poller (`cloud_sync.py` in the main HiveMGR repo) is
built to tolerate free-tier spin-down: generous timeouts, in-cycle retry for cold
starts, and backoff across cycles for a genuine outage. Upgrade to a paid always-on
plan once real shop traffic shows up — no code change needed, just the Render plan.
