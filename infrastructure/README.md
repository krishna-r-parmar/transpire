# Infrastructure

Docker and manually approved deployment configuration belongs here. The root `docker-compose.yml` is the local reference stack.

## QA deployment on EC2

The `Deploy QA` workflow targets `/home/ubuntu/transpire` on the configured
instance. SSM starts the command as root, then switches to `ubuntu`, fetches the
commit that triggered the workflow, and checks it out before running the tracked
`deploy/deploy.sh`. Before checkout, `git reset --hard HEAD` discards any staged
or unstaged edits to tracked server files. No backup or stash is created.
Ignored configuration and untracked files stay in place; a conflicting untracked
file still blocks checkout. A server-only root `deploy.sh` is not used. The
`ubuntu` user must have Git access to the repository and permission to use Docker
Compose.

Keep server configuration in these ignored files:

- `backend/.env`: passed to both the backend and email worker containers. Use
  `deploy/backend.env.example` as a reference. The production stack uses an
  existing PostgreSQL server; `DATABASE_URL` must be reachable from inside Docker
  (`localhost` would refer to the container itself).
- `frontend/.env`: supplies `NEXT_PUBLIC_API_URL` at image build time and optionally
  `NEXT_PUBLIC_CSRF_COOKIE_NAME`. Use `deploy/compose.env.example` as a reference.
- Root `.env`: optional shared Compose settings. `frontend/.env` takes precedence
  for values defined in both files.

Neither `deploy/.env` nor `backend.env` is required. Environment files are left on
the server during Git checkout and are not printed by the configuration check.
PostgreSQL must already be configured. Deployment builds the application, runs
migrations, and recreates only the backend, frontend, and email worker containers
with the new images. It finishes after that step. Nginx runs separately and is
not managed by this deployment. No orphan removal or image/cache pruning runs.

To deploy the current server checkout manually:

```bash
cd /home/ubuntu/transpire
bash deploy/deploy.sh
```
