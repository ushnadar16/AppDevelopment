# NaSCon '2026 — Multi-Sport League & Club Operations Platform

Backend: Python 3.12 · FastAPI · PostgreSQL 16 · Redis 7 (domain-event stream). Mobile: React Native (Android), in `mobile/`.

## Run the backend

```bash
cp .env.example .env              # put the team salt in DAY1_SALT (never commit it)
DAY1_SALT=<your-salt> docker compose up -d --build
curl http://localhost:8080/health # {"status":"ok"}
```

`docker compose up -d --build` starts `db` (PostgreSQL 16), `redis` and `api` (port 8080). The API waits for
Postgres, creates its schema, and seeds the baseline data at startup and on every `POST /audit/v1/reset`.
No manual steps are needed.

## Tests and coverage

```bash
./run_tests.sh            # local python3 (creates .venv-tests if needed)
./run_tests.sh --docker   # only Docker needed
./run_tests.sh --write    # also rewrite COVERAGE.json with the measured per-area figures
```

## Demo accounts (exist after every startup and every reset)

| Role | Email | Password | Scope |
|---|---|---|---|
| Platform Super-Admin | admin@nascon.test | Nascon@26 | platform-wide |
| League Organizer | organizer@nascon.test | Nascon@26 | owns `league-alpha-1` |
| Club Manager | manager@nascon.test | Nascon@26 | owns `club-alpha-1` |
| Player | player@nascon.test | Nascon@26 | `player-alpha-1` |
| General Viewer | viewer@nascon.test | Nascon@26 | read-only in `tenant-alpha` |

## Architecture

| Concern | Where |
|---|---|
| Sports as data (no sport/event-name branches) | `backend/app/sports.py` |
| Fixture algorithms: circle-method RR, Swiss (exact min-cost matching), single/double elim | `backend/app/fixtures.py` |
| Append-only event-sourced scoring, signed compensating events | `backend/app/scoring.py` |
| Standings recomputed from event logs, recursive tie-break resolution, clinched/eliminated | `backend/app/standings.py` |
| Roster transfers, loans with auto-return, immutable audit trail | `backend/app/roster.py` |
| Store: atomic reservation, mock payment gateway, signed PDF receipts | `backend/app/store.py` |
| 5-tier RBAC policy matrix, HS256 JWT (rejects alg:none/tampered/expired) | `backend/app/rbac.py` |
| Offline sync conflict resolution | `backend/app/sync.py` |
| State, PostgreSQL append-only tables (UPDATE/DELETE blocked by triggers), outbox queue → Redis Stream | `backend/app/state.py` |
| HTTP layer, rate limit, 1 MB body limit, WebSocket `/ws` | `backend/app/main.py` |

Rule checks run against an in-process projection behind a single lock (one uvicorn worker), which serialises
writes. That is the zero-oversell guarantee for the store. Every match event, roster audit entry, order and
domain event is appended to PostgreSQL by a background outbox worker. Domain events are also published to the
Redis Stream `nascon:domain-events`.

## Production API for the mobile app (`/api/v1/*`, `Authorization: Bearer <token>`)

Rate limit: 100 requests per rolling 10 s per IP (429 `RATE_LIMITED` + `Retry-After`). Errors always use
`{"error":{"code","message","details"}}`. `message` is plain language and safe to show to users.

| Method & path | Purpose |
|---|---|
| `POST /api/v1/auth/login` `{email,password}` | → `{token, user{role, tenant{name, branding{primary_color, secondary_color, logo_url}}, league_ids, club_id, player_id}}` |
| `GET /api/v1/me` | current user |
| `GET /api/v1/leagues` | leagues visible to the user |
| `GET /api/v1/fixtures?league_id=` | matches with status, score, `scheduled_at`, `venue`, `version` |
| `GET /api/v1/matches/{id}` | live score, event timeline, `pinned_product`, sport config |
| `POST /api/v1/matches/{id}/events` | organizer scoring: `{event_id, type, payload}` (same as `/audit/v1/events`) |
| `POST /api/v1/matches/{id}/pin` `{product_id}` | pin a product on a match page (broadcast on `/ws`) |
| `GET /api/v1/standings/{league_id}` | points table + qualification status + H2H |
| `GET /api/v1/clubs/{id}` | club profile, venue, staff, socials, stats, roster (`roster_league_id`) |
| `POST /api/v1/roster/transfer` | club manager: transfer / loan / release (same body as `/audit/v1/roster/transfer`) |
| `GET /api/v1/roster/history/{player_id}` | audit trail |
| `GET /api/v1/products` | catalogue with variants, price, stock |
| `POST /api/v1/checkout` | `{order_id, items, discount_code, payment{token}}`; tokens `tok_success`, `tok_declined`, `tok_capture_fail` |
| `GET /api/v1/orders/{id}/receipt.pdf` | server-generated PDF receipt |
| `POST /api/v1/offline-sync` | replay the offline queue (format below) |
| `WS /ws` | realtime messages `{"topic": "match.event_appended" \| "match.product_pinned" \| "order.status_changed" \| ..., "data": {...}}` |

The offline queue item format (Section 5.14) is
`{action_id, type: "score_event"|"roster_transfer", queued_at: "YYYY-MM-DDTHH:MM:SSZ", base_version, payload}`.
`base_version` is the match `version` (score events) or the number of audit entries for the player (roster).
Each result is `{status: applied|rejected|duplicate, resolution, error_code, server_version}`.

Emulator base URL: `http://10.0.2.2:8080`. Physical phone: `http://<laptop-LAN-IP>:8080`.
