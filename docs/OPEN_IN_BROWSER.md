# Open MYSOP in your browser

## What is available in this cloud environment

MYSOP has a complete web interface at `/`, served by the Python backend: account registration/login, recipe collection, guided food/drink SOP creation, draft submission, owner approval, ingredient costs, preparation instructions and acknowledgment of published updates.

Start it inside the cloud checkout with `bash scripts/start.sh`. It listens on port 8000. The agent can validate it with HTTP requests and Chromium inside the environment. This environment has no attached public preview or port-forwarding service, so its internal address cannot be opened from your laptop or phone. A screenshot is a record of a real browser run, not an interactive public preview.

## Open the working app on your computer

1. Clone `https://github.com/amsyarazman/MYSOP.git`. While the version 0.4 pull request is under review, use `git clone --branch codex/mysop-v04-owner-bom https://github.com/amsyarazman/MYSOP.git`. Once both source-import and version 0.4 pull requests are merged, a normal clone of `main` contains the updated app. If you already have a working Mac copy, follow [UPDATE_MAC.md](UPDATE_MAC.md) first to preserve your saved data.
2. Install **Python 3.12 or newer** if it is not already installed.
3. Open a terminal in the cloned `MYSOP` folder and use the commands for your operating system below.
4. Keep the server terminal open. In a browser **on that same computer**, enter `http://localhost:8000` in the address bar. This local address works after you start the app on your own computer; it is not a preview of the cloud container.

### macOS or Linux

```bash
cd /path/to/MYSOP
bash scripts/install.sh
bash scripts/start.sh
```

The install script detects `python3` or `python` and checks the version. To set up manually, run:

```bash
cd /path/to/MYSOP
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pytest -q
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Windows PowerShell

```powershell
cd C:\path\to\MYSOP
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

These Windows commands are provided for local setup; validation in this cloud task runs on Linux. Confirm `py -3 --version` reports Python 3.12 or newer. Directly invoking the virtual environment's Python avoids PowerShell activation restrictions.

If port 8000 is already used, stop your earlier MYSOP server or choose `--port 8080` with uvicorn and open `http://localhost:8080` on that computer. Press Ctrl+C in the server terminal to stop MYSOP. Restarting preserves data in `data/mysop.sqlite3`.

## Try the main workflow

1. The first screen shows clearly labeled sample recipes. Browse Food or Drinks and open a sample SOP.
2. Choose **Sign in → New here? Create an account**, then register with an email and a password of at least 10 characters. No email is sent.
3. Create a team. Its creator is the owner.
4. Choose **Create SOP**. Follow Basics, Ingredients, Method and Review; enter at least one ingredient and one preparation step. Costs are optional.
5. Choose **Save & publish** as the owner. Your actual recipe appears in the SOP library. Samples are replaced by real team data after sign-in.
6. To test collaboration, generate supervisor and staff invitations under **Team & invitations**. Open separate browser profiles/private windows, register separate accounts, and join the same team with those invitations. A supervisor creates and submits a draft; the owner approves it; staff receive the live update and can prepare and acknowledge that version.

For phone/tablet access on your own trusted Wi-Fi, the server binds to `0.0.0.0`. Use your computer's LAN IP and port on the other device, and allow the port through your local firewall if needed. Do not use `localhost` on the phone: that points to the phone itself. Use only test accounts/data for this unencrypted local development connection. Internet-accessible use requires an HTTPS deployment or supported preview service.

## How the cloud app is tested

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/browser_smoke.py
```

The second command requires the optional packages in `requirements-browser.txt` and system Chromium. It starts its own server on port 8011 and uses a temporary database. It tests three browser sessions at desktop, tablet and phone sizes, including login, guided authoring, costing, supervisor submission, owner return/approval, live publication, staff preparation, acknowledgment and sign-out. Actual screenshots are saved in `docs/`.

## Save the source to GitHub

The editable source is on `codex/mysop-v04-owner-bom`, retaining the original `main` commit and the source-archive commit. Use a pull request to review it before merging. For later edits, work in an existing clone and create a new branch:

```bash
git switch -c my-change
# Make changes, then test and review the exact files to commit.
.venv/bin/python -m pytest -q
git add app tests docs README.md
git diff --cached --stat
git diff --cached --check
git commit -m "Describe the change"
git push -u origin my-change
```

Open a pull request from the pushed branch to `main`. These commands require your own GitHub access. Before committing, inspect the staged file list for runtime databases, credentials and local configuration; `.gitignore` does not untrack files previously committed. If your old copy came from a ZIP, use the backup-and-clone procedure in [UPDATE_MAC.md](UPDATE_MAC.md), rather than initializing a new Git history over that folder.
