# Update your Mac without losing saved data

MYSOP stores accounts, teams, recipes, approvals and acknowledgments in SQLite,
separately from the source code. The default is `data/mysop.sqlite3`, relative to
the project directory. If you start with `MYSOP_DB` set, that path takes precedence.
The start script changes into the project directory, so a relative custom path
is resolved there. Confirm the path used by your existing server before updating.
The start script does not automatically load `.env`; keep using the same exported
variables or your existing launcher.

## 1. Stop and back up the existing copy

Stop every MYSOP server using this database with Ctrl+C in its terminal. Keep it
stopped while backing up and moving data; copying a live SQLite file alone can
miss changes in its WAL file. Do not delete any `-wal` or `-shm` companions.

On macOS, set the actual path of your existing project, then make a complete
backup outside it:

```bash
mysop_old="/absolute/path/to/MYSOP"
mysop_backup="${mysop_old}-backup-$(date +%Y%m%d-%H%M%S)"
ditto "$mysop_old" "$mysop_backup"
```

Check that `ditto` completed successfully and the backup contains your data,
configuration and any local source edits. Treat it as private: it can contain
password hashes, session data and secrets. If `MYSOP_DB` points outside the
project, back up that database and any WAL/SHM companions separately while the
app is stopped; the project backup does not include external files. Retain the
backup until you have verified your existing accounts and recipes after updating.

## 2a. If your existing copy is a Git checkout

Use these commands **after the source-import and version 0.4 pull requests have merged into `main`**:

```bash
cd "$mysop_old"
git status --short
```

If this lists changes or untracked files, preserve and resolve them first. Do not
blindly stage everything, because an older copy may lack the new ignore rules.
For a clean checkout with a local `main` branch:

```bash
git fetch origin
git switch main
git pull --ff-only origin main
bash scripts/install.sh
bash scripts/start.sh
```

If `main` does not exist locally, use `git switch --track origin/main` instead of
`git switch main`. If Git reports a conflict, divergent history or an overwrite
warning, stop and keep your backup; do not use `reset --hard`, force checkout or
`git clean`. The install script updates `.venv` and tests against temporary
databases. It does not intentionally clear your real database. The ignore rules
exclude `data/`, SQLite files, `.env` and virtual environments from new commits;
they do not protect against manual deletion or files already tracked by Git.

## 2b. If your existing copy came from a ZIP, or you want to test before merge

Keep the original folder intact and clone into a **new sibling folder**. Do not
run `git init` over the old copy or replace its contents blindly.

```bash
cd "$(dirname "$mysop_old")"
# Before the PR is merged:
git clone --branch codex/mysop-v04-owner-bom https://github.com/amsyarazman/MYSOP.git MYSOP-updated
# After merge, use a normal clone instead of the command above:
# git clone https://github.com/amsyarazman/MYSOP.git MYSOP-updated
```

Choose a different destination if `MYSOP-updated` already exists. When the old
app used the default `data/` directory, copy that complete directory into the new
clone while both copies are stopped, including any WAL/SHM companions:

```bash
ditto "$mysop_old/data" MYSOP-updated/data
cd MYSOP-updated
bash scripts/install.sh
bash scripts/start.sh
```

Run that `ditto` command only if your old `data/` directory exists. If you used a
custom database, instead copy its database and companions to a private location
and export the matching **absolute** path before startup, or continue using its
existing absolute path after backing it up. For example:

```bash
export MYSOP_DB="/absolute/path/to/your/existing/mysop.sqlite3"
bash scripts/start.sh
```

Keep using that same setting on later starts. Do not point to a new empty path:
MYSOP will create a fresh database there, which can look like lost data. Copy
private configuration such as `.env` separately if needed, and restore your
exported variables or launcher. Recreate `.venv` through the install script;
virtual environments should not be copied between project paths.

Version 0.4 adds a Bill of Materials table without removing existing users, recipes, versions or acknowledgments. Legacy prices are retained for the owner. New recipe photos and cost records live in the same SQLite database. Install the updated locked dependencies (including Pillow) before starting the new source.

## 3. Verify and retain a rollback copy

Open `http://localhost:8000` on the Mac, sign into an **existing** account and
check your team and saved recipes. `http://localhost:8000/health` should return
`{"status":"ok"}`. An HTTP health response alone does not establish that you
selected the correct data file. There is no reason to register a replacement
account if you are expecting existing data; recheck `MYSOP_DB` and the copied
directory first.

Startup applies the app's additive database upgrade, including conversion of
legacy `member` roles to `staff`. The automated tests cover that upgrade, but
keep your pre-upgrade backup. To roll back, stop the new server and restore both
the old source and the matching pre-upgrade database with its companions; do not
run old and new servers simultaneously against a database being restored.
