---
name: mysop-start
description: Start and verify the MYSOP Python web app in an existing checkout.
---

# Start MYSOP

Use the existing `/workspace/MYSOP` checkout. Cloud tasks are already isolated; do not create a Git worktree unless explicitly requested.

1. `cd /workspace/MYSOP`. Python 3.12+ is required. If `.venv/bin/python` is absent or dependencies changed, run `bash scripts/install.sh`. It installs the checked-in `requirements.lock`, checks dependencies and runs the API tests.
2. Start `bash scripts/start.sh` in a persistent terminal. It binds to `0.0.0.0:8000`; set `PORT` to change the port. Do not start a duplicate if an existing MYSOP process is healthy. Live processes must restart after snapshot restoration.
3. Internally request `/health` and verify `{"status":"ok"}`. Request `/` and verify the HTML references `/static/app.js`; confirm `/static/app.js` and `/static/style.css` return 200. `/docs` provides the API documentation.
4. Run `.venv/bin/python -m pytest -q` for the API, authorization, versioning, owner approval, costs, acknowledgments, database migration, live/replay, persistence and static assets checks.
5. For a full browser check, install optional `requirements-browser.txt`, then run `.venv/bin/python scripts/browser_smoke.py`. It uses system Chromium, an isolated temporary database, and an additional server on port 8011. It validates three browser sessions creating, reviewing, approving, preparing and acknowledging an SOP and saves screenshots under `docs/`. Never use the real database for automated tests.

The web app opens with clearly labeled sample recipes, without inserting them into the database. To use real data: create an account, create or join a team, assign supervisor/staff access, use the four-step SOP guide, save a private draft, submit as a supervisor, approve as the owner, then prepare and acknowledge as staff. Owners can generate role-specific single-use invitations and manage existing staff/supervisor roles under Team & invitations. Owners approve under Approvals. Supervisors see review notes and can revise returned drafts under My drafts. An approved new version needs a fresh staff acknowledgment.

Data persists in `data/mysop.sqlite3` or the path specified by `MYSOP_DB`. Preserve existing databases and WAL/SHM companions. There are no required external services or credentials. Never commit runtime data, session tokens, passwords or `.env` files.

The onboarding UI does not expose localhost previews. Use local requests and browser automation for validation; present screenshots when no shareable preview capability is available. Do not invent a public URL. This is a development foundation, not a production deployment.
