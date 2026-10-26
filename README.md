# Prediciotn

A football statistics and forecast web app. It shows every player and team stat and forecasts the chance a player or team reaches a stat line, with the reasons. Analysis only: no betting, odds or promotion (see `docs/03_rules_and_compliance.md`).

Stack: React (frontend), FastAPI with synchronous pymongo (backend), MongoDB. Built for [Emergent](https://emergent.sh).

## What is in this repo

| Folder | What it is | State |
|---|---|---|
| `backend/` | FastAPI app (`server.py`) and every module: accounts, 2FA, security layer, plans, Stripe, e-mail, admin (123 routes), Site Studio, popups, integrations, ingest, jobs, images, queries | Built and tested |
| `backend/soccer_brain/` | The forecast engine (Dixon-Coles, negative-binomial GLM, tactics, rotation) | Built and tested |
| `backend/tests/` | 12 self-test suites, a fake PitchAPI, and `demo_server.py` | All pass |
| `frontend/` | React app: routing for every screen, API client, auth, design tokens, crest and avatar components. **Today**, sign-in, sign-up, verify and the Markdown pages work. Every other screen is a labelled placeholder that names its spec and shows the live API answer | Scaffold for Emergent to finish |
| `docs/` | The full hand-off: product plan, design system, database, every route, ingest, engine, admin, billing, security, images, checklist, clickable admin prototype | Complete |
| `EMERGENT.md` | The prompts to give Emergent, one phase at a time | Start here |

## Run it on your computer (no keys needed)

```bash
# backend: tests, then the demo (in-memory database, simulated league)
cd backend
pip install -r requirements.txt
bash run_tests.sh
# frontend
cd ../frontend && yarn install && yarn build && cd ../backend
python3 tests/demo_server.py          # open http://localhost:8001  (demo owner: owner@example.com / demo-owner-pass-1)
```

For frontend work with hot reload: run the demo server, then `cd frontend && REACT_APP_BACKEND_URL=http://localhost:8001 yarn start`.
(Cross-origin cookies need `ALLOWED_ORIGINS=http://localhost:3000` and `COOKIE_SECURE=0` in the backend environment.)

## Environment

- `backend/.env.example`: every variable. Only `MONGO_URL`, `DB_NAME`, `APP_ENCRYPTION_KEY`, `CRON_SHARED_SECRET`, `PUBLIC_BASE_URL`, `ADMIN_EMAIL` and `ADMIN_INITIAL_PASSWORD` go in `.env`. Provider keys (PitchAPI, Stripe, Resend, API-Football) are entered in Admin → Keys and stored encrypted.
- `frontend/.env.example`: `REACT_APP_BACKEND_URL` (empty when the app and the API share one domain, as on Emergent).

## Rules that override everything

1. `docs/03_rules_and_compliance.md`: banned words, honest labels, locked settings. `yarn check-copy` scans the frontend.
2. `docs/15_security_and_privacy.md`: sessions in an HttpOnly cookie, never in localStorage; server checks every permission; Markdown rendered without raw HTML.
3. The data provider's field names are unverified until check A in `docs/08`. Never invent a key name.

## What is still open (owner decisions)

- PitchAPI field names (check A), cup and European fixtures for the rotation calendar, and the real-data backtest (`docs/18`).
- API-Football terms before turning player photos on (`docs/19`). Run `backend/check_apifootball.py` once.
- Stripe stays in test mode and `features.billing` off until you decide.
