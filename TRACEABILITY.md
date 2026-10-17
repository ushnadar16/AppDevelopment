# Traceability Matrix

| ID | Requirement | Source files | Automated tests |
|---|---|---|---|
| FR-1.1 | Multi-sport taxonomy as data, mystery sport, event-sourced scoring, compensating events | `backend/app/sports.py`, `backend/app/scoring.py`, `backend/app/main.py` (`/audit/v1/sports`, `/events`, `/score`) | `tests/test_scoring.py` (`test_mystery_sport_flow`, `test_innings_model`, `test_round_model`, `test_sport_validation`, `test_idempotency`, `test_reference_vectors`) |
| FR-1.2 | League setup scoped to seasons, points and tie-break configuration | `backend/app/standings.py` (`register_league`) | `tests/test_standings.py::test_league_registration_errors`, `test_custom_points_and_tiebreak_order` |
| FR-1.3 | Round robin, Swiss, single and double elimination; match status state machine | `backend/app/fixtures.py`, `backend/app/scoring.py` (`check_rules`) | `tests/test_fixtures.py` (all), `tests/test_scoring.py::test_mystery_sport_flow` (illegal transitions) |
| FR-1.4 | Standings, recursive tie-breakers incl. 3-way mini-league, H2H, clinched/eliminated | `backend/app/standings.py` (`compute_standings`) | `tests/test_standings.py::test_three_way_h2h`, `test_draw_lots_and_status`, `test_innings_nrr`, `test_undecided_counts_as_remaining` |
| FR-2.1 | Club profiles, white-label tenants, tenant isolation | `backend/app/state.py` (tenants, clubs), `backend/app/main.py` (`/api/v1/clubs`) | `tests/test_rbac.py::test_login_and_production_api`, `test_matrix` |
| FR-2.2 | Transfers, loans with auto-return, releases, rule order, immutable audit trail | `backend/app/roster.py` | `tests/test_roster.py` (all) |
| FR-2.3 | Store catalogue, variants, discounts, mock gateway, order states, PDF receipt | `backend/app/store.py` | `tests/test_store.py` (all) |
| FR-5.1 | Five-tier RBAC policy matrix, scoped permissions, negative tests | `backend/app/rbac.py`, `backend/app/main.py` (probe routes) | `tests/test_rbac.py::test_matrix` (every role × boundary), `test_bad_tokens` |
| NFR-3 | Concurrency correctness: 20 buyers, 1 unit | `backend/app/store.py` (`checkout`: atomic reserve → gateway → commit/release) | `tests/test_store.py::test_concurrent_last_unit` |
| NFR-4 | Offline tolerance: queued actions sync with conflict handling | `backend/app/sync.py`, `mobile/` | `tests/test_sync.py::test_offline_sync` |
| NFR-5 | Security: JWT verification, rate limiting, input validation, 413 body limit, RBAC | `backend/app/rbac.py`, `backend/app/main.py` (`guard`, `read_json`), `backend/app/util.py` | `tests/test_rbac.py::test_bad_tokens`, `test_rate_limit_and_body_size`, `tests/test_scoring.py::test_sport_validation` |
| NFR-7 | Reproducibility: one command brings up the stack and seeds baseline data | `docker-compose.yml`, `backend/Dockerfile`, `backend/app/state.py` (`reset`, `init_db`) | `tests/conftest.py` (reset before each test), `run_tests.sh` |
