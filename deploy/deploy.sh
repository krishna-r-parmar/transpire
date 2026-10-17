#!/usr/bin/env bash
# Rebuild and restart TRANSPIRE from the commit currently checked out in this
# repo. The GitHub Actions Deploy workflow runs this on EC2 through AWS SSM
# after `git checkout <sha>`; it can also be run by hand.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"

# One server environment file supplies service settings and public build inputs.
ENV_FILE="$REPO_DIR/.env"
[[ -r "$ENV_FILE" && -s "$ENV_FILE" ]] || {
  echo "Missing, empty, or unreadable $ENV_FILE; run deployment with the required GitHub Actions secrets" >&2
  exit 1
}

compose() {
  docker compose --project-name transpire --project-directory "$DEPLOY_DIR" --env-file "$ENV_FILE" \
    -f "$DEPLOY_DIR/docker-compose.prod.yml" "$@"
}

command -v docker >/dev/null
docker compose version >/dev/null
docker info >/dev/null
# Validate without printing resolved environment values into deployment logs.
compose config --quiet

echo "==> Deploying $(git -C "$DEPLOY_DIR" log -1 --format='%h %s')"

echo "==> Building images"
compose build --pull

echo "==> Running database migrations"
compose run --rm --no-deps backend alembic upgrade head

echo "==> Restarting containers"
# Target application services explicitly; leave the separate Nginx container alone.
compose up -d --no-build --no-deps backend frontend email-worker

echo "==> Application containers restarted"
