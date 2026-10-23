# MYSOP 0.4 verification — 23 October 2026

The next version separates owner costing from operational SOPs, adds compressed square photos and provides a vertical, paginated staff reader.

## Results

- `bash scripts/install.sh`: installs the updated lockfile including Pillow 13.0.0, checks dependencies and runs the API tests on Python 3.12.14 / Linux.
- `.venv/bin/python -m pytest -q`: **29 passed**. One upstream Starlette TestClient deprecation warning; no failures.
- `.venv/bin/python scripts/browser_smoke.py`: **passed** with system Chromium. Three isolated owner/supervisor/staff browser sessions cover registration, role invitations, supervisor authoring with photo upload, private drafts, return/revision/approval, live delivery, preparation, acknowledgment persistence, sign-out and sign-in.
- The owner browser creates ingredient pack prices and packaging/labour amounts **per serving** in the separate Bill of Materials window. A two-serving recipe totals MYR 4.50 / MYR 2.25 per serving. Supervisor/staff interfaces expose no price inputs or costing window.
- API tests reject non-owner and cross-team bill reads/writes, reject stale concurrent saves, and verify that normal SOP/draft/review/history/event responses exclude structured cost fields. Cost updates preserve published instructions and staff acknowledgments. Draft and published quantities are costed separately using the same working rates.
- Photo tests cover publication/restart persistence, square dimensions, file-size limits, corrupt/non-JPEG data, metadata-stripping re-encoding, removal, and detailed image compression. The browser crops a 900 × 600 image into a 512 × 512 square thumbnail.
- Long-content browser checks traverse every page at **390 × 844**, **320 × 568** and **844 × 390**. They verify no horizontal/vertical overflow in the reader, and that all long procedure, ingredient and safety text remains present across pages. No JavaScript page errors.
- Legacy database tests preserve original publications and prices through repeated startup and retain subsequently saved owner costs.
- `pip check`, JavaScript syntax checks and Git whitespace checks pass.

Tests use temporary databases. Existing Mac data has not been accessed or changed. Mac-specific commands are documented but were not executed on a Mac.

## Screenshots and use

The browser run refreshes `preview-approval.png`, `preview-staff.png` and `preview-bom.png`. They are records of the actual interface, not public previews. Staff use Next/Back in the SOP reader; authoring, review and costing forms may scroll.

Install and start with `bash scripts/install.sh` and `bash scripts/start.sh`. Open the app on the same machine; no public cloud preview is configured. For updates to an existing Mac installation, stop the app and follow [UPDATE_MAC.md](UPDATE_MAC.md), retaining the project/database backup and the existing `MYSOP_DB` setting.

## Review scope

Branch `codex/mysop-v04-owner-bom` builds on the source-import branch from PR #4, preserving its history. Since PR #4 is still open, the next-version PR targets `codex/mysop-source-review` so reviewers see only the version 0.4 changes. Merge the source import first, then retarget the next-version PR to `main` if needed. No automatic merge or production deployment is performed.
