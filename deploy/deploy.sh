#!/usr/bin/env bash
# Roll out an image tag that is already loaded on this host. The GitHub Actions
# deploy workflow streams the images here and then runs this script over SSH.
set -euo pipefail

TAG="${1:?usage: deploy/deploy.sh <image-tag>}"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$DEPLOY_DIR/.env"
HEALTH_TIMEOUT_SECONDS=180
RELEASES_TO_KEEP=5
IMAGES=(transpire-backend transpire-frontend)

compose() {
  docker compose --project-directory "$DEPLOY_DIR" -f "$DEPLOY_DIR/docker-compose.prod.yml" "$@"
}

env_value() {
  grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2- || true
}

set_env_value() {
  if grep -qE "^$1=" "$ENV_FILE"; then
    sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"
  fi
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

# Keep the newest releases (and anything in use) so rollbacks need no rebuild.
prune_old_releases() {
  local image tag
  for image in "${IMAGES[@]}"; do
    docker image ls "$image" --format '{{.Tag}}' | tail -n +$((RELEASES_TO_KEEP + 1)) | while read -r tag; do
      [[ "$tag" == "$TAG" || "$tag" == "$CURRENT_TAG" ]] && continue
      docker image rm "$image:$tag" >/dev/null 2>&1 || true
    done
  done
  docker image prune -f >/dev/null
}

[[ -f "$DEPLOY_DIR/backend.env" ]] || { echo "Missing $DEPLOY_DIR/backend.env (the Deploy workflow writes it from GitHub settings)" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || cp "$DEPLOY_DIR/compose.env.example" "$ENV_FILE"

for image in "${IMAGES[@]}"; do
  if ! docker image inspect "$image:$TAG" >/dev/null 2>&1; then
    echo "Image $image:$TAG is not on this host. Run the Deploy workflow for that commit." >&2
    exit 1
  fi
done

CURRENT_TAG="$(env_value IMAGE_TAG)"
export IMAGE_TAG="$TAG"

echo "==> Running database migrations"
compose run --rm --no-deps backend alembic upgrade head

echo "==> Starting containers"
compose up -d --no-build --remove-orphans

echo "==> Waiting for health checks"
if ! wait_for_health; then
  echo "!! Health checks failed for $TAG" >&2
  compose ps >&2
  compose logs --tail 80 backend frontend >&2
  if [[ -n "$CURRENT_TAG" && "$CURRENT_TAG" != "$TAG" ]]; then
    echo "!! Restoring containers to $CURRENT_TAG (database migrations are not reverted)" >&2
    IMAGE_TAG="$CURRENT_TAG" compose up -d --no-build --remove-orphans
  fi
  exit 1
fi

if [[ "$CURRENT_TAG" != "$TAG" ]]; then
  set_env_value PREVIOUS_IMAGE_TAG "$CURRENT_TAG"
fi
set_env_value IMAGE_TAG "$TAG"

echo "==> Pruning old releases (keeping $RELEASES_TO_KEEP)"
prune_old_releases

compose ps
echo "==> Deployed $TAG"
