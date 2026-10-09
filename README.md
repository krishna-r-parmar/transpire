# TRANSPIRE

TRANSPIRE, a name formed from Transform and Inspire, is a multi-tenant organisational idea-management platform for Operational Excellence.

## Local development

```bash
npm install
npm run dev
```

The frontend runs at `http://localhost:3000`. The FastAPI service can be started independently from `backend/`, or the full stack can be run with Docker Compose after copying `.env.example` to `.env`.

For backend-only development:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -e 'backend[dev]'
cp -n backend/.env.example backend/.env
cd backend
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_development.py
.venv/bin/uvicorn app.main:app --reload
```

Set `DEV_ADMIN_PASSWORD` and `OUTBOX_ENCRYPTION_KEY` in the ignored `backend/.env` before running the seed command. Sign in at `http://localhost:3000/sign-in` with `DEV_ADMIN_EMAIL` and that password; TRANSPIRE resolves the account's active workspace memberships without using the email domain. Run `.venv/bin/python scripts/process_email_outbox.py --watch` in another terminal when developing without Docker Compose.

Backend quality checks:

```bash
backend/.venv/bin/ruff check backend/app backend/migrations backend/tests backend/scripts
backend/.venv/bin/pytest -q backend/tests
```

For the Docker Compose development stack, migrate and seed once before starting all services:

```bash
docker compose up -d database
docker compose build
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python scripts/seed_development.py
docker compose up
```

See [Project.md](./Project.md) for the business phases, architecture, security model, and delivery plan.
