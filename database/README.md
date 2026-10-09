# Database

PostgreSQL is the system of record. Alembic migrations live in `backend/migrations/`. Tenant-owned tables must include `tenant_id`, tenant-scoped indexes, and PostgreSQL Row-Level Security policies.
