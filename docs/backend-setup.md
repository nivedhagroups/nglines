# Backend Setup

## Local Docker

1. Copy `.env.example` to `.env` and set unique `JWT_SECRET`, `OTP_HMAC_SECRET`, and an initial Super Admin email or phone.
2. Build and start PostgreSQL and the API with `docker compose up --build -d`.
3. Generate and review the first migration from the ORM models, then apply it:

   ```powershell
   docker compose run --rm backend alembic revision --autogenerate -m "initial schema"
   docker compose run --rm backend alembic upgrade head
   ```

4. Create Chamber Bricks, the initial Super Admin, company settings, and standard expense categories:

   ```powershell
   docker compose run --rm backend python -m app.bootstrap
   ```

5. Open `http://localhost:8000/docs` for the development OpenAPI UI.

Development OTP codes are printed by the console provider. Production must set `OTP_DELIVERY` to a `module:ProviderClass` implementing `send(destination, channel, code)`, set `PUSH_DELIVERY=firebase`, configure Firebase Application Default Credentials, use unique secrets, and keep persistent volumes backed up. Console OTP delivery is rejected in production.

`/data/files` is a persistent Docker volume intended for Phase 1 files. Do not remove that volume to clear estimate artifacts; use a retention job that deletes expired estimate PDF files and share links while keeping estimate records.

The initial Alembic revision must be generated and reviewed before deployment. Do not use `Base.metadata.create_all()` as a production migration strategy.