# LeadDesk AI 3.0 — Professional Foundation

This is the first real PySide6/Qt foundation release. It is a separate application from Version 2.4, so keep your working Version 2.4 folder unchanged until migration is confirmed.

## Cost
The included development tools are free. Paid AI, SMS, email, mailing, cloud, and data-provider services are not required for this foundation release.

## First-time Windows setup
1. Extract this ZIP into a normal folder, not inside the ZIP viewer.
2. Double-click `setup_windows.bat`. It creates a private virtual environment and installs PySide6 and pytest.
3. Double-click `run_tests.bat`. The expected result is `9 passed`.
4. Double-click `run_app.bat`.

## Move your Version 2.4 data
1. In the new app, open **Migration & Backup**.
2. Click **Migrate Version 2 Database**.
3. Select the database from the working Version 2.4 folder, normally `data\leaddesk_v2.db`.
4. Confirm the replacement.
5. The Dashboard should show your 50 properties.

The app creates a verified backup before replacing an existing Version 3 database and also backs up when the app closes.

## What is genuinely included
- PySide6 modern desktop shell
- Git-ready `src/` project layout
- SQLite schema v5 compatible with the Version 2 data model
- Version 2 database migration and property-count validation
- Dashboard and searchable property table
- Note creation with activity/audit history
- Verified SQLite backups
- Rotating application logs
- Compliance guard service
- MAO calculation service
- Automated tests
- Windows setup, run, test, Git-init, and executable-build scripts

## Not included yet
No automatic SMS, email, direct mail, AI replies, offer sending, contract signing, title verification, or legal conclusions. Those are later integrations and will require service accounts, compliance review, and explicit approval controls.
