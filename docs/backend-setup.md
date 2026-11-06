# Backend Setup

# Backend Setup

## Local Windows Setup (No Docker)

Prerequisites: Python 3.12, PostgreSQL 18, and Node.js for the mobile client. This workspace has a dedicated local PostgreSQL cluster on port `5433`; it is loopback-only and separate from both the Windows PostgreSQL service and Docker's database.

The local database directory is `%LOCALAPPDATA%\NivedhaGroups\PostgreSQL\18\data`. Start it in its own terminal and leave that terminal open while using the app:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\postgres.exe' -D "$env:LOCALAPPDATA\NivedhaGroups\PostgreSQL\18\data" -p 5433 -h 127.0.0.1
```

This development cluster uses the dedicated `nivedha` role with trust authentication, and listens only on loopback; it does not use the installed Windows PostgreSQL service's `postgres` password. The root `.env` points the backend at `postgresql+asyncpg://nivedha@127.0.0.1:5433/nivedha` and stores generated PDFs under `backend/storage/files`. Do not replace this with the Docker hostname `db` for a local run. To use a different local PostgreSQL instance, set `DATABASE_URL` locally to that instance's role, password, port, and database; do not send its password in chat.

Create the venv and install dependencies once:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Apply migrations from `backend/`, so Alembic resolves its relative script directory correctly:

```powershell
Push-Location backend
$env:PYTHONPATH = $PWD
$env:DATABASE_URL = 'postgresql+asyncpg://nivedha@127.0.0.1:5433/nivedha'
.\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
Pop-Location
```

Bootstrap Chamber Bricks and the initial Super Admin if needed. A one-time temporary password is printed only when a password is first generated; change it immediately at first sign-in:

```powershell
$env:PYTHONPATH = "$PWD\backend"
backend\.venv\Scripts\python.exe -m app.bootstrap
```

Run the API from the repository root; keep this terminal running while using the app:

```powershell
$env:PYTHONPATH = "$PWD\backend"
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload --reload-dir backend\app
```

Local API docs are at `http://localhost:8000/docs`; Android emulator API calls use `http://10.0.2.2:8000/api/v1`. The SQLite-free local PostgreSQL database is separate from Docker; the Docker database container was left intact as a backup/source.

PDF files are generated on invoice/estimate creation and updates, stored date-wise under `backend/storage/files/documents/YYYY/MM/DD/<business-id>/`, and shared by the mobile native share sheet. Back up this folder with the database.

## Docker (Optional)

Docker Compose remains available but is not required for local development. Compose uses its own database and `/app/storage/files` mount. Do not run both backends on port `8000` simultaneously.

Sign in with the Super Admin email/phone and temporary password. A forced password-change screen appears before the rest of the app is available. Passwords require at least 12 characters and are hashed with Argon2id. Only Admin and Super Admin can create users; only Super Admin can assign the Super Admin role. New users receive unique temporary passwords and must change them at first sign-in. Email invitations are sent through SendGrid SMTP; set `SMTP_PASSWORD` to a SendGrid API key and verify the `SMTP_FROM_EMAIL` sender in SendGrid. Without email delivery, the creating administrator receives the temporary password once in the API response.

Production must set `PUSH_DELIVERY=firebase`, configure Firebase Application Default Credentials, use a unique JWT secret, and keep persistent volumes backed up.

Do not use `Base.metadata.create_all()` as a production migration strategy. Keep credentials and the local `.env` out of source control.