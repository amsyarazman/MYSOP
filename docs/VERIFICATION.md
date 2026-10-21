# MYSOP verification — 21 October 2026

These checks apply to the uploaded `MYSOP-source.zip`, whose SHA-256 is
`1cc120137e3d9551c78a80d571ccd8dc832c0777c01237ef96cdbf95def4bf38`.
It is byte-for-byte identical to the archive on `mysop-download-20261021`
(commit `fbaaa23750786770156893adda35c72267dc2d59`). Any newer Mac edits outside
that ZIP are not included. MYSOP includes a browser interface served by FastAPI
at `/`.

## Results

- Ran `bash scripts/install.sh` with Python 3.12.14, installing the locked dependencies and executing all Python tests.
- The existing static-assets test verified `/`, `/health`, `/static/app.js` and `/static/style.css`; health response: `{"status":"ok"}`.
- `.venv/bin/python -m pip check`: no broken requirements.
- `.venv/bin/python -m pytest -q`: **12 passed**. One upstream Starlette TestClient deprecation warning; no failures.
- `.venv/bin/python scripts/browser_smoke.py`: **passed** using real system Chromium, with desktop (1440×1000), tablet (1024×900) and phone (390×844) browser sessions.
- Browser workflow covered account registration, role invitations, guided SOP creation and ingredient costing, private drafts, supervisor submission, owner return/revision/approval, live delivery of published SOPs, staff preparation, acknowledgment persistence, publication of a second version, sign-out and signing back into the existing account. No JavaScript page errors or horizontal overflow.
- Automated workflow tests used temporary databases, separate from the running app's data.
- Shell syntax checks passed for installation and startup scripts.

The browser smoke test started and stopped `bash scripts/start.sh` on port 8011
with a temporary database. No Mac database was available or modified.

The screenshots in this folder were refreshed by the browser test. They are
records of the working interface, not interactive previews.

## Browser access

No browser preview or inbound port-forwarding service is attached to this cloud
environment. Its internal port 8000 is reachable by tools within the environment,
but no working public preview URL is available. Binding to `0.0.0.0` alone does
not expose it to your browser. The process must be restarted if the cloud
environment stops or is restored.

For interactive testing, use the source checkout, install Python 3.12 or newer,
and run the installation/startup commands in
[OPEN_IN_BROWSER.md](OPEN_IN_BROWSER.md), then open `http://localhost:8000` on
that same computer. Register an account, create a team, create an SOP and choose
**Save & publish** as its owner. The published recipe appears in the SOP library.
Windows PowerShell commands are included in the guide; this verification ran
on Linux.

## GitHub preparation

The cloud checkout's `codex/mysop-source-review` branch is based on the existing
source-archive branch, preserving both its commit and the original `origin/main`
history and placeholder file. The archive was unpacked into editable source.
The import includes expanded ignore rules and Mac update guidance. The branch
replaces the ZIP with editable source, tests, dependencies, scripts and docs so
the application can be reviewed and installed directly from a clone.

The archive contains application code, tests, locked dependencies, scripts,
documentation and screenshots. It excludes Git metadata, virtual environments,
runtime databases, caches, logs and secrets. Future Mac source transfers must
also exclude those private/runtime files. See
[UPDATE_MAC.md](UPDATE_MAC.md) for backup and update instructions.
