# Backend — NaSCon '26 Multi-Sport League & Club Operations Platform

This document explains how the backend is built, why it is built that way, and how to run, test and debug it.
For the binding API contract, see the Part I specification PDF. This file maps that contract onto the code.

**Stack:** Python 3.12 · FastAPI · Uvicorn (1 worker) · PostgreSQL 16 · Redis 7 · Docker Compose.
No BaaS, no third-party fixture libraries. Everything runs self-hosted from `docker-compose.yml`.

---

## 1. Quick start (what the grader runs)

From the **repository root**:

```bash
cp .env.example .env                                  # put the team salt from the slip in DAY1_SALT
DAY1_SALT=<your-salt> docker compose up -d --build     # builds the API image, starts db + redis + api
curl http://localhost:8080/health                      # -> {"status":"ok"}
```

- First build takes about 90 s on a laptop. `/health` turns 200 a few seconds after the containers start.
  The grader allows 10 minutes for the build and 120 s for health.
- No manual steps: the API waits for Postgres, creates its schema and seeds the baseline data by itself.
- `DAY1_SALT` is read **only** from the environment. It is never hard-coded or committed.

Stop and wipe everything:

```bash
docker compose down -v
```

### Prerequisites on a Mac (Apple Silicon)

The Homebrew `docker` formula is just the CLI. You also need an engine and the Compose and buildx plugins:

```bash
brew install docker docker-compose docker-buildx colima
mkdir -p ~/.docker/cli-plugins
ln -sfn /opt/homebrew/opt/docker-compose/bin/docker-compose ~/.docker/cli-plugins/docker-compose
ln -sfn /opt/homebrew/opt/docker-buildx/bin/docker-buildx  ~/.docker/cli-plugins/docker-buildx
colima start --cpu 4 --memory 6 --disk 60 --vm-type vz --vz-rosetta   # once per reboot: `colima start`
```

---

## 2. Running without Docker (fast local dev loop)

If `DATABASE_URL` is unset, the backend runs fully **in memory**: same rules, no persistence. This is the
quickest way to iterate.

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
cd backend
DAY1_SALT=demo-salt ../.venv/bin/uvicorn app.main:app --port 8080 --reload
```

To use a real database locally, start only the infrastructure and point the API at it:

```bash
docker compose up -d db redis          # note: compose does not publish 5432/6379 to the host by default
```

**Port 8080 must be free** before `docker compose up`. A leftover local uvicorn on 8080 will make the
`api` container fail to bind (`lsof -nP -iTCP:8080 -sTCP:LISTEN` shows who holds it).

---

## 3. Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `DAY1_SALT` | yes | HMAC key for event and receipt signatures (Section 5.3). UTF-8 bytes, used verbatim. |
| `DATABASE_URL` | no | `postgresql://…`. Set by compose. If unset, the backend runs in memory. |
| `REDIS_URL` | no | `redis://…`. Set by compose. Domain events go to the Redis Stream `nascon:domain-events`. |
| `JWT_SECRET` | no | HS256 signing key for JWTs. If empty, a key is derived from `DAY1_SALT`. |

`.env.example` at the repository root lists all of them and contains no real salt.

---

## 4. Architecture

```
            HTTP :8080 (FastAPI, 1 uvicorn worker)
   ┌───────────────────────────────────────────────────────────┐
   │ main.py  middleware: 1 MB body limit (413), /api/v1 rate   │
   │          limit (100 req / 10 s / IP, 429 + Retry-After)    │
   │          error envelope {"error":{code,message,details}}   │
   │   /audit/v1/*  grader interface                            │
   │   /api/v1/*    production API for the mobile app (JWT)     │
   │   /ws          realtime broadcast (WebSocket)              │
   └──────────────┬────────────────────────────────────────────┘
                  │ every write happens under ONE re-entrant lock
   ┌──────────────▼────────────────────────────────────────────┐
   │ state.py  in-process projection (source for rule checks)  │
   │   sports.py  fixtures.py  scoring.py  standings.py         │
   │   roster.py  store.py     rbac.py     sync.py   util.py    │
   └──────────────┬────────────────────────────────────────────┘
                  │ write-behind outbox thread
        ┌─────────▼─────────┐        ┌──────────────────────────┐
        │ PostgreSQL 16     │        │ Redis 7 Stream           │
        │ append-only tables│        │ nascon:domain-events     │
        │ (UPDATE/DELETE    │        │ (internal job/event queue)│
        │  blocked by trigger)       └──────────────────────────┘
        └───────────────────┘
```

### Key design decisions

1. **Single writer lock (NFR-3, no overselling).** All state changes run under one `threading.RLock` in a
   single uvicorn worker, so checks and reservations are atomic. The 20-buyer burst on the last unit gives
   exactly one 201 and nineteen 409s, with `stock=0, reserved=0`. This is also why the Dockerfile pins
   `--workers 1`. **Do not raise the worker count.**
2. **Event sourcing.** Match scores are never stored as counters. `GET /score` and `GET /standings` rebuild
   everything from the append-only event log on every call. Corrections are new `compensation` events. The
   original row is never modified, and Postgres triggers reject UPDATE/DELETE on the log tables.
3. **Sports are data (FR-1.1).** Football, basketball, cricket and esports are seeded through the same
   validator as a "mystery sport" posted to `/audit/v1/sports`. Domain code branches only on the
   **scoring model** (`event` / `innings` / `round`) and on config fields. It never branches on a sport or
   event name, which would cost 8 points as hard-coded sport logic.
4. **Write-behind persistence.** Rule checks read the in-memory projection, which is fast and deterministic.
   An outbox thread appends every event, audit entry, order and domain event to Postgres and to the Redis
   stream. `/health` returns 200 only once the database is reachable and the baseline is seeded.
5. **Deterministic signatures.** `util.py` implements Appendix A exactly:
   `HMAC_SHA256(DAY1_SALT, id + "|" + canonical_json(payload))` in lowercase hex. Canonical JSON uses sorted
   keys, no whitespace, and `ensure_ascii=False`.

---

## 5. Module guide

| File | Requirement | What it does |
|---|---|---|
| `app/main.py` | all | FastAPI app: every route, middleware (413, rate limit), error envelope, JWT auth for `/api/v1`, WebSocket hub. |
| `app/util.py` | 5.2, 5.3 | `ApiError`, canonical JSON, HMAC signing, id/date/timestamp validation. |
| `app/sports.py` | FR-1.1, 5.6 | Sport schema validation, the four seed sports as data, scoring-model helpers. |
| `app/fixtures.py` | FR-1.3, 5.7 | Round robin (circle method, byes, legs, withdrawals with `void_all` / `forfeit_remaining`), Swiss (exact round 1, then minimum-cost rematch-free pairing with bye fallback and `NO_VALID_PAIRING`), single elimination (recursive seeding, byes, third-place match), double elimination (WR/LR/GF, bracket reset). `networkx` is used only as a generic matching solver, not as a fixture generator. |
| `app/scoring.py` | FR-1.1, 5.9 | Match state machine (`upcoming → in_progress → completed`), event validation, innings/round limits, compensation, idempotency by `event_id`, score projection. |
| `app/standings.py` | FR-1.2, FR-1.4, 5.8, 5.10 | League registration. Standings recomputed from logs, with recursive tie-break resolution (`h2h_points → h2h_diff → overall_diff → scored → fair_play → draw_lots`), the full H2H matrix, net run rate, and clinched/eliminated status. |
| `app/roster.py` | FR-2.2, 5.11 | Transfer, loan and release with the 8 rule checks in spec order, loan auto-return via `as_of`, deferral when a match is in progress, immutable audit trail, idempotency by `request_id`. |
| `app/store.py` | FR-2.3, 5.12 | Catalogue, `WELCOME10` discount, atomic reservation, mock gateway (`tok_success`, `tok_declined`, `tok_capture_fail`), order state machine with domain events, signed receipt and hand-built PDF. |
| `app/rbac.py` | FR-5.1, 5.13 | HS256 JWT (rejects `alg:none`, tampered and expired tokens), a data-driven 5-role policy matrix and tenant isolation (403 for cross-tenant access, 404 only for ids that don't exist). |
| `app/sync.py` | NFR-4, 5.14 | Offline replay: sort by `queued_at`, results `applied`, `rebased_append`, `duplicate` and `server_wins`, plus `INVALID_BASE_VERSION`. |
| `app/state.py` | NFR-7 | Global state, baseline seed (tenants, store, RBAC scenario, 5 demo users), Postgres schema and outbox, Redis stream. |

---

## 6. Endpoints

### Grader interface — `/audit/v1/*` (no auth, no rate limit)

| Method & path | Purpose |
|---|---|
| `GET /health` | 200 `{"status":"ok"}` once the DB is reachable and the baseline is seeded |
| `POST /audit/v1/reset` | Wipe state and reseed. Optional body `{"seed":42,"stock":{…}}`. Repeated calls leave identical state. |
| `POST /audit/v1/sports` | Create a mystery sport from JSON |
| `POST /audit/v1/fixtures` | `round_robin` / `swiss` / `single_elim` / `double_elim` (pure computation) |
| `POST /audit/v1/leagues` | Register teams, fixtures, points and tie-break configuration |
| `POST /audit/v1/events` | Append a match event or compensation (signed) |
| `GET /audit/v1/score/{match_id}` | Score projection rebuilt from the log |
| `GET /audit/v1/standings/{league_id}` | Table, H2H, clinched/eliminated |
| `POST /audit/v1/roster/setup` | Build a roster scenario |
| `POST /audit/v1/roster/transfer` | Transfer, loan or release |
| `GET /audit/v1/roster/history/{player_id}?as_of=YYYY-MM-DD` | Audit trail and loan auto-return |
| `POST /audit/v1/checkout` | Concurrency-safe purchase with signed PDF receipt |
| `GET /audit/v1/inventory/{variant_id}` | `{variant_id, stock, reserved}` |
| `POST /audit/v1/rbac-matrix` | JWTs for all 5 roles plus scenario ids |
| `/audit/v1/rbac/*` | 7 authorization probe routes (P1–P7) |
| `POST /audit/v1/offline-sync` | Replay queued offline actions |
| `GET /api/v1/ping` | Rate-limit probe |

### Production API — `/api/v1/*` (for the mobile app)

`Authorization: Bearer <token>` from `POST /api/v1/auth/login`. Rate limited to 100 requests per 10 s per IP.
The full table is in the repository-root `README.md`. Summary: `auth/login`, `me`, `leagues`, `fixtures`,
`matches/{id}` (+ `/events`, `/pin`), `standings/{id}`, `clubs/{id}`, `roster/transfer`,
`roster/history/{id}`, `products`, `checkout`, `orders/{id}/receipt.pdf`, `offline-sync`, and `WS /ws`.

Mobile base URL: emulator `http://10.0.2.2:8080`; physical phone `http://<laptop-LAN-IP>:8080` (on the team hotspot).

### Demo accounts (exist after every startup and every reset)

| Role | Email | Password |
|---|---|---|
| Platform Super-Admin | admin@nascon.test | Nascon@26 |
| League Organizer (owns `league-alpha-1`) | organizer@nascon.test | Nascon@26 |
| Club Manager (owns `club-alpha-1`) | manager@nascon.test | Nascon@26 |
| Player (`player-alpha-1`) | player@nascon.test | Nascon@26 |
| General Viewer | viewer@nascon.test | Nascon@26 |

---

## 7. Tests and coverage

```bash
./run_tests.sh            # local python3; creates .venv-tests if needed
./run_tests.sh --docker   # needs only Docker (python:3.12-slim)
./run_tests.sh --write    # also rewrites COVERAGE.json with the measured figures
```

- 144 pytest tests in `tests/`, one file per graded area, including negative RBAC tests for every role boundary.
- `tools/coverage_areas.py` folds coverage.py output into the six graded areas, written to `COVERAGE.json`
  at the root. The grader voids an area's bonus if the real figure is more than 2 points below the declared
  one. **Re-run `./run_tests.sh --write` after changing code.**
- `TRACEABILITY.md` (repository root) maps every FR/NFR id to source files and tests.

### Manual smoke checks against a running stack

```bash
B=http://localhost:8080
curl -s -XPOST $B/audit/v1/reset | jq
curl -s -XPOST $B/audit/v1/leagues -H 'content-type: application/json' -d '{"league_id":"lg-1","sport_id":"football","teams":["t1","t2"],"fixtures":[{"match_id":"m1","home":"t1","away":"t2"}],"qualification":{"spots":1}}'
curl -s -XPOST $B/audit/v1/events -H 'content-type: application/json' -d '{"event_id":"e0","match_id":"m1","type":"match_start","payload":{}}'
curl -s -XPOST $B/audit/v1/events -H 'content-type: application/json' -d '{"event_id":"evt-1","match_id":"m1","type":"score","payload":{"team_id":"t1","event_type":"goal"}}'
# with DAY1_SALT=demo-salt the signature must be 972a8b558690b19121cc5bea84978f85e8eb15a3735018db36616bab1d7ec501 (Appendix A, vector 1)
curl -s $B/audit/v1/score/m1 | jq
curl -s $B/audit/v1/standings/lg-1 | jq
```

Verified on 2026-10-17 against the Docker stack with `DAY1_SALT=demo-salt`: both Appendix A vectors, reset
idempotency, mystery sport, innings overs, all four fixture formats, roster edge case 6, the 20-way checkout
burst (1×201, 19×409, stock 0, reserved 0), PDF receipt text and signature, the 75-cell RBAC matrix,
`alg:none` and tampered tokens, 413, rate limit and recovery, offline-sync conflicts and duplicates, and all
5 demo logins.

---

## 8. Hidden edge cases (Section 6) and where they live

| # | Edge case | Handled in |
|---|---|---|
| 1 | Odd-team round robin with a mid-season withdrawal | `fixtures.py`: one bye per round; `void_all` / `forfeit_remaining` |
| 2 | Swiss round where no rematch-free pairing exists | `fixtures.py`: global search over bye candidates → 409 `NO_VALID_PAIRING` |
| 3 | Double elimination bracket reset | `fixtures.py`: `GF2.conditional=true`, `required` set only after GF1 |
| 4 | Three-way tie needing the H2H mini-league | `standings.py`: `resolve(group)` restarts from the first criterion on every split |
| 5 | Result corrected after qualification was decided | `scoring.py` compensation + `standings.py` full recompute |
| 6 | Transfer on the last window day during a live match | `roster.py`: `state:"deferred_until_match_end"` + `blocking_match_id` |

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `failed to connect to the docker API at unix:///var/run/docker.sock` | No engine is running. Run `colima start` (or start Docker Desktop). |
| `unknown shorthand flag: 'd' in -d` on `docker compose` | Compose plugin missing. See §1 prerequisites. |
| `api` container exits with "address already in use" | Something else holds port 8080: `lsof -nP -iTCP:8080 -sTCP:LISTEN`. |
| `/health` stays 503 | Postgres is not ready yet or unreachable. Check `docker compose logs db api`. |
| Signatures differ from the grader's | Wrong `DAY1_SALT`. It must match the slip exactly (not trimmed, not hex-decoded). |
| Coverage bonus at risk | `./run_tests.sh --write`, then commit `COVERAGE.json`. |
