#!/usr/bin/env bash
# Rebuild and restart TRANSPIRE from the commit currently checked out in this
# repo. The GitHub Actions Deploy workflow runs this on EC2 through AWS SSM
# after `git checkout <sha>`; it can also be run by hand.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HEALTH_TIMEOUT_SECONDS=180

compose() {
  docker compose --project-directory "$DEPLOY_DIR" -f "$DEPLOY_DIR/docker-compose.prod.yml" "$@"
}

wait_for_health() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT_SECONDS))
  until curl -fsS http://127.0.0.1:8000/health/ready >/dev/null 2>&1 \
    && curl -fsS -o /dev/null http://127.0.0.1:3000/ 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 5
  done
}

[[ -f "$DEPLOY_DIR/.env" ]] || { echo "Missing $DEPLOY_DIR/.env (copy compose.env.example)" >&2; exit 1; }
[[ -f "$DEPLOY_DIR/backend.env" ]] || { echo "Missing $DEPLOY_DIR/backend.env (copy backend.env.example)" >&2; exit 1; }

echo "==> Deploying $(git -C "$DEPLOY_DIR" log -1 --format='%h %s')"

echo "==> Building images"
compose build --pull

echo "==> Running database migrations"
compose run --rm --no-deps backend alembic upgrade head

echo "==> Restarting containers"
compose up -d --no-build --remove-orphans

echo "==> Waiting for health checks"
if ! wait_for_health; then
  echo "!! Health checks failed" >&2
  compose ps >&2
  compose logs --tail 80 backend frontend >&2
  exit 1
fi

echo "==> Cleaning up old images and build cache"
docker image prune -f >/dev/null
docker builder prune -f --filter until=168h >/dev/null

compose ps
echo "==> Deployed"
