# TRANSPIRE Backend

The backend is a FastAPI modular monolith organised around business domains.

## Current domain boundaries

- `tenants`: tenant lifecycle, stable shortnames, settings, and branding
- `identity`: users, memberships, roles, sessions, invitations, and password recovery
- `communications`: provider-neutral transactional email and delivery records
- `configuration`: tenant-owned organisational/classification registers and versioned workflow contracts
- `ideas`: idea-management domain placeholder for the next Phase 1 capability slice
- `core`: configuration, PostgreSQL sessions, health checks, API composition, and tenant context

Views translate HTTP requests. Controllers own application use cases and transaction boundaries. Services hold domain policy. Repositories isolate persistence. Models and schemas remain owned by their domain.

Tenant-aware APIs are available under `/api/v1/t/{tenant_shortname}`. The shortname is resolved to the immutable tenant UUID before handlers run or PostgreSQL RLS context is set. Central sign-in authenticates the global account first, loads active memberships, enters the only workspace automatically, or returns a short-lived single-use workspace-selection challenge when several memberships exist. Email domains never resolve tenants. Authentication uses Argon2 password hashes, opaque server-side sessions, HttpOnly cookies, double-submit CSRF protection, database-backed request throttles, temporary account lockouts, tenant and membership checks, session revocation, and authentication audit events.

## Local sign-in

Configure `DEV_ADMIN_PASSWORD` in the ignored `backend/.env`, then run from `backend/`:

```bash
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_development.py
.venv/bin/uvicorn app.main:app --reload
```

The seed is development-only and idempotent. It creates the `DEV_TENANT_SLUG` workspace and a Tenant Admin using `DEV_ADMIN_EMAIL`. Open `http://localhost:3000/sign-in`; a single active membership is selected automatically. Keep `SESSION_COOKIE_SECURE=false` locally and set it to `true` behind HTTPS in production.

In the route inventory below, insert `/t/{tenant_shortname}` after `/api/v1` for every tenant-scoped route. Central sign-in, workspace selection, password-reset requests, and invitation inspection/acceptance remain global because they establish or recover tenant context securely.

Authentication routes:

- `POST /api/v1/auth/sign-in`
- `POST /api/v1/auth/select-workspace`
- `GET /api/v1/auth/sso/global/start` — begin Microsoft sign-in from the shared sign-in page
- `GET /api/v1/auth/sso/global/callback` — discover eligible SSO workspaces from the verified Entra identity
- `GET|POST /api/v1/auth/sso/global/workspaces` — securely choose when that identity has several workspaces
- `GET /api/v1/auth/session`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/password-reset/request`
- `POST /api/v1/auth/password-reset/complete`
- `GET /api/v1/t/{tenant_shortname}/auth/sso/status` — public tenant sign-in policy
- `GET /api/v1/t/{tenant_shortname}/auth/sso/start` — begin Microsoft Entra OIDC
- `GET /api/v1/t/{tenant_shortname}/auth/sso/callback` — validate Entra and issue the existing tenant session
- `GET /api/v1/t/{tenant_shortname}/auth/workspaces` — active workspaces for the signed-in user
- `POST /api/v1/auth/invitations/inspect`
- `POST /api/v1/auth/invitations/accept`

Administration routes:

- `GET|POST /api/v1/platform/tenants` — platform administrators only
- `PATCH /api/v1/platform/tenants/{tenant_id}/status` — platform administrators only
- `DELETE /api/v1/platform/tenants/{tenant_id}` — recoverably removes a tenant
- `POST|DELETE /api/v1/platform/tenants/{tenant_id}/invitations/{invitation_id}` — resend or revoke the first-administrator invitation
- `GET /api/v1/platform/tenants/{tenant_id}/members` — platform administrator member oversight
- `PATCH /api/v1/platform/tenants/{tenant_id}/members/{membership_id}/status` — platform administrator member lifecycle control
- `GET /api/v1/admin/members` — tenant administrators only
- `GET /api/v1/admin/roles` — tenant administrators only
- `GET|PUT /api/v1/admin/sso` — inspect readiness or configure the Entra directory
- `GET /api/v1/admin/sso/validate` — validate configuration with the current tenant administrator
- `POST /api/v1/admin/sso/activate` — atomically require SSO and queue active-user notices
- `POST /api/v1/platform/tenants/{tenant_id}/sso/recovery` — issue restricted recovery
- `GET|POST /api/v1/admin/invitations` — list or create invitations
- `POST|DELETE /api/v1/admin/invitations/{invitation_id}` — resend or revoke an invitation
- `PATCH /api/v1/admin/members/{membership_id}/status` — activate or deactivate a member
- `GET|POST /api/v1/admin/configuration/master-data/{kind}` — list or create sites, departments, categories, subcategories, and process areas
- `PATCH /api/v1/admin/configuration/master-data/{kind}/{item_id}` — update configuration lifecycle state
- `GET /api/v1/admin/configuration/workflows/contracts` — inspect versioned approval contracts
- `POST /api/v1/admin/configuration/workflows/{workflow_id}/versions` — create the next draft contract
- `POST /api/v1/admin/configuration/workflows/{workflow_id}/versions/{version_id}/publish` — publish a draft and retire the former active version
- `GET|PUT /api/v1/admin/configuration/idea-bank-policy` — inspect or update tenant-wide Idea Bank visibility

Idea routes:

- `GET /api/v1/ideas/submission-catalog` — active tenant sites, departments, URS categories, subcategories, guidance, and process areas
- `GET /api/v1/ideas/home-summary` — the signed-in user’s ideas and pending assigned approvals
- `GET /api/v1/ideas/{idea_id}` — owner, assigned-approver, or Tenant Admin idea detail
- `POST /api/v1/ideas` — create a draft
- `PUT /api/v1/ideas/{idea_id}` — update the current user’s draft
- `POST /api/v1/ideas/{idea_id}/submit` — submit and bind to the published workflow contract
- `POST /api/v1/ideas/{idea_id}/approvals/{stage_id}` — record the assigned approver’s decision
- `PUT /api/v1/ideas/{idea_id}/charter` — save the approved idea owner’s charter draft
- `POST /api/v1/ideas/{idea_id}/charter/submit` — submit and lock the completed charter
- `GET /api/v1/ideas` — tenant-wide Idea Bank response filtered by the tenant visibility policy

Tenant provisioning creates a unique shortname, system roles, a published `Demo Approval` workflow contract, the invited first administrator membership, and a single-use invitation in one transaction. Email domains are not collected or inferred. Invitation links expire after `INVITATION_EXPIRY_HOURS`; sensitive links are encrypted in the outbox. Resending invalidates earlier links and replaces any unsent invitation email; revoking invalidates the link and removes its queued email. Tenant removal is a soft lifecycle state that disables the workspace, sessions, and open invitations instead of erasing organisational records.

## Microsoft Entra SSO

Configure `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, and the externally reachable `PUBLIC_API_URL`. A tenant administrator then supplies the organisation's Entra directory ID in **Admin → Configuration → Authentication**, completes a real administrator validation, and performs the guarded cutover. Activation changes authentication routing only: existing users, memberships, roles, sessions, and owned business records remain in place. Existing sessions expire normally, while new sessions use Entra. Each active member receives one idempotent `sso_migration` email for that activation.

Register both the shared callback (`{PUBLIC_API_URL}/auth/sso/global/callback`) and each tenant administration callback (`{PUBLIC_API_URL}/t/{tenant_shortname}/auth/sso/callback`) as **Web** redirect URIs in Entra. Locally, the shared callback is `http://localhost:8000/api/v1/auth/sso/global/callback`. The shared entry point discovers the workspace from Entra's verified directory and object identity; it enters a single matching workspace immediately and presents a workspace choice only when several active SSO workspaces match.

Platform administrators can issue a short-lived, single-use recovery link to an active tenant administrator. Redeeming it creates an `sso_recovery` scoped session, which normal application dependencies reject; it can only replace the Entra directory configuration and require validation again.

Cookie-authenticated `POST`, `PUT`, `PATCH`, and `DELETE` requests must echo the readable `CSRF_COOKIE_NAME` cookie in the `X-CSRF-Token` header. Authentication bootstrap and token-completion routes are exempt. Configure `ALLOWED_HOSTS`, `CORS_ORIGINS`, and `CORS_ORIGIN_REGEX` explicitly for each environment. Production startup rejects insecure session cookies, missing outbox encryption, and wildcard trusted hosts.

## Password recovery and transactional outbox

Password-reset requests always return the same accepted response. Active accounts receive a 30-minute, single-use token; only its SHA-256 hash is stored in the token table. Completing a reset consumes the token, revokes every existing session for that tenant membership, records an audit event, and queues an account-security email.

Email jobs are inserted in the same transaction as the business change. Sensitive template values, including reset links, are encrypted using `OUTBOX_ENCRYPTION_KEY` rather than stored in plaintext. Generate a development key with:

```bash
.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Keep this key in the ignored `backend/.env` or a production secret manager. Losing or rotating it makes already-queued sensitive messages unreadable.

Set `PUBLIC_APP_URL` to the externally reachable shared TRANSPIRE origin. Tenant links are generated beneath `/t/{shortname}`; invitation acceptance remains on the shared origin because its single-use token securely carries tenant context. Use `http://localhost:3000` locally and the central TRANSPIRE application origin in production.

Run the delivery worker separately from the API:

```bash
.venv/bin/python scripts/process_email_outbox.py --watch
```

Workers use PostgreSQL `FOR UPDATE SKIP LOCKED`, an expiring delivery lease, and exponential retries. Multiple worker replicas can process the queue concurrently. Docker Compose starts the `email-worker` service automatically after the database is available.

## Database migrations

Run migrations from `backend/`:

```bash
.venv/bin/alembic upgrade head
.venv/bin/alembic check
```

The migrations create tenant, identity, authentication-audit, and email-delivery tables. PostgreSQL Row-Level Security is enabled for tenant-scoped operational tables. A transaction sees no tenant rows until the application calls `apply_tenant_to_transaction()` with a tenant UUID resolved from a path shortname.

`resolve_tenant_by_slug(text)` is the narrow database function used before tenant context exists. It returns only tenant identity and lifecycle information. The legacy hostname table and resolver remain for one rollback window but are no longer used by application code.

## SMTP configuration

Local backend credentials belong in `backend/.env`, which is ignored by Git. A shareable template is available at `backend/.env.example`.

Keep `EMAIL_BACKEND=console` while developing without a mail server. To send real mail, set:

```dotenv
EMAIL_BACKEND=smtp
EMAIL_FROM_ADDRESS=no-reply@your-company.com
EMAIL_FROM_NAME=TRANSPIRE
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_USERNAME=your-username
SMTP_PASSWORD=your-password-or-app-secret
SMTP_START_TLS=true
SMTP_USE_TLS=false
```

Use either STARTTLS, commonly port 587, or implicit TLS, commonly port 465. Do not enable both.

## Transactional email templates

Templates live in `app/domains/communications/templates/` and always provide HTML and plain-text alternatives:

- `invitation`
- `password_reset`
- `idea_submission_confirmation`
- `project_charter_ready`
- `account_security`

Render safe sample previews with:

```bash
.venv/bin/python scripts/render_email_previews.py
```

Previews are written to `/tmp/transpire-email-previews`. The renderer uses strict variables and HTML autoescaping so missing template data fails early and user-provided values cannot inject markup.
