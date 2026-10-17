#!/usr/bin/env bash
# Rebuild and restart TRANSPIRE from the commit currently checked out in this
# repo. The GitHub Actions Deploy workflow runs this on EC2 through AWS SSM
# after `git checkout <sha>`; it can also be run by hand.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"

# Root settings are optional; frontend settings override them for build inputs.
COMPOSE_ENV_ARGS=()
[[ ! -f "$REPO_DIR/.env" ]] || COMPOSE_ENV_ARGS+=(--env-file "$REPO_DIR/.env")
COMPOSE_ENV_ARGS+=(--env-file "$REPO_DIR/frontend/.env")

compose() {
  docker compose --project-directory "$DEPLOY_DIR" "${COMPOSE_ENV_ARGS[@]}" \
    -f "$DEPLOY_DIR/docker-compose.prod.yml" "$@"
}

for file in "$REPO_DIR/backend/.env" "$REPO_DIR/frontend/.env"; do
  [[ -r "$file" ]] || { echo "Missing or unreadable $file" >&2; exit 1; }
done

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
